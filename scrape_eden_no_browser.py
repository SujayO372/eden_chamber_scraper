import re, sys, time, csv
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from configparser import ConfigParser

ALPHAS = ["0-9"] + [chr(c) for c in range(ord("a"), ord("z")+1)]

DETAIL_HREF_PATTERNS = (
    "/list/member", "/list/Member",
    "/list/details", "/list/Details",
    "memberdetails", "/Directory/member/", "mid=", "bid="
)

SKIP_SUBSTR = ("/info", "/member/newmemberapp", "/MemberToMember", "/membertomember", "/login")

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

@dataclass
class Row:
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

def same_origin(u, origin):
    pu = urlparse(u)
    return (pu.scheme, pu.netloc) == (origin.scheme, origin.netloc)

def is_detail(u: str) -> bool:
    ul = u.lower()
    if any(b in ul for b in SKIP_SUBSTR):
        return False
    return any(p.lower() in ul for p in DETAIL_HREF_PATTERNS)

def get(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def discover_member_links(html: str, base: str, origin) -> set:
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href: 
            continue
        u = urljoin(base, href)
        if same_origin(u, origin) and is_detail(u):
            links.add(u)
    # Fallback: common card containers (if detail anchors are nested)
    if not links:
        for sel in (".gz-directory-card a[href]", ".mn-listing a[href]", ".directory-listing a[href]", ".business-listing a[href]"):
            for a in soup.select(sel):
                u = urljoin(base, a.get("href",""))
                if same_origin(u, origin) and is_detail(u):
                    links.add(u)
    return links

def parse_member(html: str, url: str) -> Row:
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
        lbl = soup.find(string=re.compile(r"Phone", re.I))
        if lbl and lbl.parent: phone = txt(lbl.parent)

    email = ""
    a = soup.select_one("a[href^='mailto:']")
    if a: email = a.get("href","").replace("mailto:","").strip()
    if not email:
        em = soup.find(string=re.compile(r"@"))
        if em and em.parent: email = txt(em.parent)

    website = ""
    for a in soup.select("a[href]"):
        h = a["href"]
        if h.startswith("http") and not h.startswith("mailto:") and not h.startswith("tel:"):
            if not any(s in h for s in ("facebook.com","instagram.com","twitter.com","linkedin.com","pinterest.com")):
                website = h; break
            if not website: website = h

    address = ""
    city = state = postal_code = ""
    for n in soup.select("address, .address, .mn-address, .company-address, .profile-address, .gz-address"):
        t = txt(n)
        if len(t) > 10:
            address = t
            break
    if address:
        m = re.search(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)", address)
        if m:
            address, city, state, postal_code = [x.strip() for x in m.groups()]

    description = ""
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"): description = meta["content"].strip()
    if not description:
        description = maybe([".company-description", ".profile-description", ".mn-description", ".gz-description"])

    return Row(
        source_list_url="", member_url=url, name=name, categories=categories, phone=phone,
        email=email, website=website, address=address, city=city, state=state, postal_code=postal_code,
        description=description
    )

def run(base_list_url: str, user_agent: str):
    origin = urlparse(base_list_url)
    base = f"{origin.scheme}://{origin.netloc}"
    seeds = [f"{base}/list/search?sa=true", f"{base}/list/searchalpha/0-9"] + [f"{base}/list/searchalpha/{c}" for c in ALPHAS]
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    all_member_links = set()

    print("[*] Discovering member pages…")
    for u in seeds:
        try:
            html = get(s, u)
        except Exception as e:
            print("[skip]", u, e); 
            continue
        found = discover_member_links(html, u, origin)
        print(f"  {u} -> {len(found)} links")
        all_member_links |= found

    print(f"[*] Total unique member pages: {len(all_member_links)}")
    rows = []
    for i, murl in enumerate(sorted(all_member_links), 1):
        try:
            html = get(s, murl)
            r = parse_member(html, murl)
            r.source_list_url = base_list_url
            rows.append(r)
        except Exception as e:
            print("[member skip]", murl, e)
        if i % 20 == 0:
            print(f"  parsed {i}/{len(all_member_links)} profiles")

    out_dir = Path("data"); out_dir.mkdir(exist_ok=True)
    out_csv = out_dir / ("eden-chamber-static-" + time.strftime("%Y%m%d-%H%M%S") + ".csv")
    df = pd.DataFrame([asdict(r) for r in rows]).drop_duplicates(subset=["member_url"])
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"[✓] Saved {len(df)} rows -> {out_csv}")

if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read("config.ini")
    url = cfg.get("app", "urls").split(",")[0].strip()
    ua = cfg.get("app", "user_agent", fallback="Mozilla/5.0")
    run(url, ua)

