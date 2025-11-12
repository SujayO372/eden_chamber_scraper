# pw_scrape_eden.py
import csv, re, time
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup

ALPHAS = ["0-9"] + [chr(c) for c in range(ord("a"), ord("z")+1)]

CARD_SELECTORS = ",".join([
    ".gz-directory-card",      # GrowthZone
    ".mn-listing",             # ChamberMaster legacy
    ".directory-listing",
    ".business-listing",
])

DETAIL_ANCHOR_SEL = ",".join([
    "a[href*='/list/Details']",
    "a[href*='memberdetails']",
    "a[href*='/Directory/member/']",
    "a[href*='/member/']",
    "a[href*='/members/']",
])

def norm(s: str) -> str:
    import re
    return re.sub(r"\s+"," ", (s or "").strip())

def is_member_detail(url: str) -> bool:
    u = url.lower()
    if any(bad in u for bad in ("/info", "/member/newmemberapp", "/membertomember", "/login")):
        return False
    return any(p in u for p in (
        "/list/details", "/member/", "/members/", "memberdetails",
        "mid=", "bid=", "/directory/member/"
    ))

def extract_cards_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    links = set()
    # links inside cards
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
    # fallback: any detail-like anchor
    for a in soup.select(DETAIL_ANCHOR_SEL):
        href = a.get("href")
        if not href: 
            continue
        absu = urljoin(base_url, href)
        if is_member_detail(absu):
            links.add(absu)
    return sorted(links)

def extract_member(html: str, url: str):
    soup = BeautifulSoup(html, "lxml")
    def txt(n): return norm(n.get_text(" ", strip=True)) if n else ""
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
        if len(t)>10: address = t; break
    if address:
        m = re.search(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)", address)
        if m:
            address, city, state, postal_code = [x.strip() for x in m.groups()]
    description = ""
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"): description = meta["content"].strip()
    if not description:
        description = maybe([".company-description", ".profile-description", ".mn-description", ".gz-description"])
    return {
        "member_url": url, "name": name, "categories": categories, "phone": phone,
        "email": email, "website": website, "address": address, "city": city,
        "state": state, "postal_code": postal_code, "description": description
    }

def autoscroll(page, max_rounds=40, per_round_ms=300):
    last_h = 0
    stagnant = 0
    for i in range(max_rounds):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(per_round_ms)
        h = page.evaluate("document.body.scrollHeight")
        if h <= last_h:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
            last_h = h

def run(root_url: str):
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    seeds = [f"{base}/list/search?sa=true", f"{base}/list/searchalpha/0-9"] + [f"{base}/list/searchalpha/{ch}" for ch in ALPHAS]
    member_links = set()
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # make it visible for now
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(45000)

        for u in seeds:
            print("[alpha] goto:", u)
            try:
                page.goto(u, wait_until="domcontentloaded")
            except Exception as e:
                print("[alpha] WARN load:", e)

            try:
                page.wait_for_selector(CARD_SELECTORS, timeout=6000)
                print("[alpha] cards detected")
            except Exception:
                print("[alpha] cards not detected yet; scrolling")
            autoscroll(page, max_rounds=50, per_round_ms=250)
            html = page.content()
            links = extract_cards_links(html, u)
            print(f"[alpha] {u} -> {len(links)} links")
            member_links.update(links)

        print("[alpha] total unique links:", len(member_links))

        # Visit each profile
        for i, murl in enumerate(sorted(member_links)):
            print(f"[profile {i+1}/{len(member_links)}] {murl}")
            try:
                page.goto(murl, wait_until="domcontentloaded")
                page.wait_for_timeout(300)  # small settle
                html = page.content()
                rows.append(extract_member(html, murl))
            except Exception as e:
                print("[profile] WARN:", e)

        ctx.close()
        browser.close()

    # write CSV
    out = "eden_chamber_playwright.csv"
    print("[csv] writing", out, "rows:", len(rows))
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["member_url"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("[done]")

if __name__ == "__main__":
    run("https://business.edenareachamber.com/list")

