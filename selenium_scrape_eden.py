# selenium_scrape_eden.py
import csv, time, re
from urllib.parse import urljoin, urlparse
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

ALPHAS = ["0-9"] + [chr(c) for c in range(ord("a"), ord("z")+1)]
CARD_SELECTORS = [".gz-directory-card", ".mn-listing", ".directory-listing", ".business-listing"]
DETAIL_SEL = ["a[href*='/list/Details']", "a[href*='memberdetails']", "a[href*='/Directory/member/']", "a[href*='/member/']", "a[href*='/members/']"]

def is_member_detail(url: str) -> bool:
    u = url.lower()
    if any(bad in u for bad in ("/info", "/member/newmemberapp", "/membertomember", "/login")):
        return False
    return any(p in u for p in ("/list/details", "/member/", "/members/", "memberdetails", "mid=", "bid=", "/directory/member/"))

def norm(s: str) -> str:
    return re.sub(r"\s+"," ", (s or "").strip())

def extract_links(html: str, base: str):
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for sel in CARD_SELECTORS:
        for card in soup.select(sel):
            a = card.select_one("a[href]")
            if a:
                href = urljoin(base, a.get("href"))
                if is_member_detail(href):
                    links.add(href)
    for sel in DETAIL_SEL:
        for a in soup.select(sel):
            href = urljoin(base, a.get("href"))
            if is_member_detail(href):
                links.add(href)
    return sorted(links)

def extract_member(html: str, url: str):
    from bs4 import BeautifulSoup
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
    email = ""
    a = soup.select_one("a[href^='mailto:']")
    if a: email = a.get("href","").replace("mailto:","").strip()
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
        m = re.search(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\\d{4})?)", address)
        if m:
            address, city, state, postal_code = [x.strip() for x in m.groups()]
    return {"member_url": url, "name": name, "categories": categories, "phone": phone, "email": email, "website": website, "address": address, "city": city, "state": state, "postal_code": postal_code}

def main():
    root = "https://business.edenareachamber.com/list"
    parsed = urlparse(root)
    base = f"{parsed.scheme}://{parsed.netloc}"
    seeds = [f"{base}/list/search?sa=true", f"{base}/list/searchalpha/0-9"] + [f"{base}/list/searchalpha/{ch}" for ch in ALPHAS]

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options, headless=False)
    driver.set_page_load_timeout(45)

    links = set()
    for u in seeds:
        print("[alpha] goto:", u)
        driver.get(u)
        for _ in range(40):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.3)
        html = driver.page_source
        found = extract_links(html, u)
        print(f"[alpha] {u} -> {len(found)} links")
        links.update(found)

    rows = []
    for i, murl in enumerate(sorted(links)):
        print(f"[profile {i+1}/{len(links)}] {murl}")
        driver.get(murl)
        time.sleep(0.3)
        rows.append(extract_member(driver.page_source, murl))

    driver.quit()
    out = "eden_chamber_selenium.csv"
    print("[csv] writing", out, "rows:", len(rows))
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["member_url"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("[done]")

if __name__ == "__main__":
    main()

