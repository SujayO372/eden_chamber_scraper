# pw_probe.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

def main():
    print("[probe] starting...")
    with sync_playwright() as p:
        print("[probe] launching chromium...")
        browser = p.chromium.launch(
            headless=False,  # set to False so you can actually see the window
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(20000)

        def goto(url, label):
            print(f"[probe] goto {label}: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded")
                print("[probe] title:", page.title())
            except PWTimeout:
                print(f"[probe] TIMEOUT loading {label}")

        goto("https://example.com", "example")
        goto("https://business.edenareachamber.com/list", "eden list")
        input("[probe] Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
