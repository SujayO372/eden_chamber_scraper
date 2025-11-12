import argparse
from pathlib import Path
import asyncio
import pandas as pd
from datetime import datetime

from .config import Settings
from .chamber_scraper import ChamberScraper

def parse_args():
    p = argparse.ArgumentParser(description="Scrape ChamberMaster-style business listings to CSV.")
    p.add_argument("--config", type=str, default="config.ini", help="Path to config.ini")
    p.add_argument("--verbose", action="store_true", help="Print crawl progress")
    p.add_argument("--engine", choices=["httpx","playwright"], default="httpx", help="Fetcher engine")
    return p.parse_args()

async def async_main(config_path: Path, verbose: bool, engine: str):
    settings = Settings(config_path)
    if engine == "playwright":
        # Run the *sync* Playwright scraper off the event loop
        from .playwright_scraper import crawl_with_playwright
        all_records = []
        for url in settings.urls:
            print(f"\n[Playwright] Crawling: {url}")
            recs = await asyncio.to_thread(
                crawl_with_playwright,
                url,
                settings.user_agent or None,   # user_agent
                True                            # headless
            )
            all_records.extend(recs)

        if not all_records:
            print("No records scraped.")
            return

        df = pd.DataFrame([r.__dict__ for r in all_records])
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_csv = settings.output_dir / f"eden-chamber-scrape-{ts}.csv"
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"✅ Saved {len(df)} records to {out_csv}")
        return


    scraper = ChamberScraper(
        urls=settings.urls,
        timeout=settings.timeout,
        concurrency=settings.concurrency,
        user_agent=settings.user_agent,
        max_retries=settings.max_retries,
        respect_robots=settings.respect_robots,
        verbose=verbose,
    )
    records = await scraper.run()
    if not records:
        print("No records scraped.")
        return

    df = pd.DataFrame([r.__dict__ for r in records])
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_csv = settings.output_dir / f"eden-chamber-scrape-{ts}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"✅ Saved {len(df)} records to {out_csv}")

def main():
    args = parse_args()
    asyncio.run(async_main(Path(args.config), args.verbose, args.engine))

if __name__ == "__main__":
    main()
