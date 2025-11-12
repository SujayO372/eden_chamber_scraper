# scraper/playwright_scraper.py
from dataclasses import dataclass
from typing import List, Optional, Set
import re, time
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup

def normalize_whitespace(s: str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (s or "").strip())

@dataclass
class MemberRecord:
    source_list_url: str
    member_url: str
    name: str = ""
    categories: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    description: str = ""

ALPHAS = ["0-9"] + [chr(c) for c in range(ord("a"), ord("z")+1)]

CARD_SELECTORS = ",".join([
    ".gz-directory-card",      # GrowthZone
    ".mn-listing",             # ChamberMaster legacy
    ".directory-listing",
    ".business-listing"
])

DETAIL_ANCHOR_SEL = ",".join([
    "a[href*='/list/Details']",
    "a[href*='memberdetails']",
    "a[href*='/Directory/member/']",
    "a[href*='/member/']",
    "a[href*='/members/']",
])

def is_member_detail(url: str) -> bool:
    u = url.lower()
    if any(bad in u for bad in ("/info", "/member/newmemberapp", "/membertomember", "/login")):
        return False
    return any(p in u for p in (
        "/list/details", "/member/", "/members/", "memberdetails",
        "mid=", "bid=", "/directory/member/"
    ))

def extract_cards_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: Set[str] = set()

    # Links inside known card containers
    for card in soup.select(CARD_SELECTORS):
        a = card.select_one("a[href]")
        if not a: 
            continue
        href = a.get("href")
        if not href:
            continue
        absu = urljoin(base_url, href)
        if is_member_detail(absu):
            links.add(absu)

    # Fallback: explicit detail anchors anywhere
    for a in soup.select(DETAIL_ANCHOR_SEL):
        href = a.get("href")
        if not href:
            continue
        absu = urljoin(base_url, href)
        if is_member_detail(absu):
            links.add(absu)

    return sorted(links)

def extract_member(html: str, url: str) -> MemberRecord:
    soup = BeautifulSoup(html, "lxml")
    def txt(n): return normalize_whitespace(n.get_text(" ", strip=True)) if n else ""
    def maybe(sels):
        for sel in sels:
            n = soup.select_one(sel)
            if n: return txt(n)
        return ""

    name = maybe(["h1", ".company-name", ".member-name", ".mn-title", ".profile h1", "header h1"])

    cats = set()
    for sel in [".categories", ".profile-categories", ".mn-categories", ".business-categories", ".cat-links"]:
        for n in soup.select(sel):
            t = txt(n)
            if t: cats.add(t)
    categories = "; ".join(sorted(cats))

    phone = ""
    a = soup.select_one("a[href^='tel:']")
    if a: phone = a.get("href","").replace("tel:","").strip()
    if not phone:
        lab = soup.find(string=re.compile(r"Phone", re.I))
        if lab and lab.parent: phone = txt(lab.parent)

    email = ""
    a = soup.select_one("a[href^='mailto:']")
    if a: email = a.get("href","").replace("mailto:","").strip()
    if not email:
        em = soup.find(string=re.compile(r"@"))
        if em and em.parent: email = txt(em.parent)

    website = ""
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("http") and not href.startswith("mailto:") and not href.startswith("tel:"):
            if not any(s in href for s in ["facebook.com","instagram.com","twitter.com","linkedin.com"]):
                website = href; break
            if not website: website = href

    address = ""
    city = state = postal_code = ""
    for n in soup.select("address, .address, .mn-address, .company-address, .profile-address, .gz-address"):
        t = txt(n)
        if len(t) > 10: address = t; break
    if address:
        m = re.search(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)", address)
        if m:
            address, city, state, postal_code = [x.strip() for x in m.groups()]

    description = ""
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"): description = meta["content"].strip()
    if not description:
        description = maybe([".company-description", ".profile-description", ".mn-description", ".gz-description"])

    return MemberRecord(
        source_list_url="", member_url=url, name=name, categories=categories, phone=phone,
        email=email, website=website, address=address, city=city, state=state,
        postal_code=postal_code, description=description
    )

def _autoscroll(page, max_rounds: int = 30, per_round_ms: int = 350) -> None:
    """Scroll until page height stops increasing or rounds exhausted."""
    last_height = 0
    stagnant = 0
    for i in range(max_rounds):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(per_round_ms)
        height = page.evaluate("document.body.scrollHeight")
        if height <= last_height:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
        last_height = height

def crawl_with_playwright(root_url: str, user_agent: Optional[str] = None, headless: bool = True, timeout_ms: int = 45000) -> List[MemberRecord]:
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    member_links: Set[str] = set()
    records: List[MemberRecord] = []

    print("[PW] Launching browser (headless=%s)..." % headless)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(
            user_agent=user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            viewport={"width": 1366, "height": 900},
        )
        # speed up by blocking images/fonts
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image","font","media") else route.continue_())
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        def safe_goto(url: str, label: str):
            print(f"[PW] goto: {label} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PWTimeout:
                print(f"[PW][WARN] Timeout on {label} DOMContentLoaded, trying 'load'...")
                try:
                    page.goto(url, wait_until="load", timeout=timeout_ms)
                except PWTimeout:
                    print(f"[PW][WARN] Load still timed out for {label}, continuing best-effort.")

        # 1) Visit root once (mainly for connectivity/log)
        safe_goto(root_url, "root")
        try:
            page.wait_for_selector(CARD_SELECTORS, timeout=3000)
            print("[PW] card selector present on root.")
        except PWTimeout:
            print("[PW] no cards on root (expected).")

        # Build seeds A–Z + show-all
        seeds = [f"{base}/list/search?sa=true", f"{base}/list/searchalpha/0-9"] + [f"{base}/list/searchalpha/{ch}" for ch in ALPHAS]

        # 2) Collect member links from each seed
        for u in seeds:
            safe_goto(u, "alpha")
            # Try to ensure listings render
            try:
                page.wait_for_selector(CARD_SELECTORS, timeout=6000)
                print("[PW] directory cards detected.")
            except PWTimeout:
                print("[PW] cards not detected yet, will scroll anyway.")
            _autoscroll(page, max_rounds=40, per_round_ms=300)
            html = page.content()
            links = extract_cards_links(html, u)
            print(f"[PW] {u} -> {len(links)} links")
            for l in links:
                member_links.add(l)

        print(f"[PW] Total unique member links: {len(member_links)}")

        # 3) Visit each member profile and extract details
        for idx, murl in enumerate(sorted(member_links)):
            safe_goto(murl, f"profile {idx+1}/{len(member_links)}")
            html = page.content()
            rec = extract_member(html, murl)
            rec.source_list_url = root_url
            records.append(rec)
            if (idx+1) % 20 == 0:
                print(f"[PW] scraped {idx+1}/{len(member_links)} profiles...")

        context.close()
        browser.close()

    return records
