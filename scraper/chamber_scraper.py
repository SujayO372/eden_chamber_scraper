import re
import asyncio
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .utils import normalize_whitespace, same_origin, is_member_detail_url, looks_like_email, looks_like_phone

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


class ChamberScraper:
    def __init__(self, urls: List[str], *, timeout: int = 20, concurrency: int = 8,
                 user_agent: Optional[str] = None, max_retries: int = 3,
                 respect_robots: bool = True, verbose: bool = False):
        self.urls = urls
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrency)
        self.headers = {"User-Agent": user_agent or "Mozilla/5.0 (compatible; EdenChamberScraper/1.5)"}
        self.max_retries = max_retries
        self.respect_robots = respect_robots
        self.verbose = verbose

    def _log(self, *a):
        if self.verbose:
            print(*a)


    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, headers=self.headers, http2=True, follow_redirects=True)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _fetch(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        async with self.semaphore:
            r = await client.get(url)
            r.raise_for_status()
            return r
            

    # Add these helpers near the top of the file (or anywhere above _collect_member_links)

    def _is_alpha_or_showall(url: str) -> bool:
        u = url.lower()
        return ("/list/searchalpha/" in u) or ("/list/search?sa=true" in u)

    DETAIL_PATTERNS = (
        "/list/details", "/list/member", "/member/", "/members/", "memberdetails",
        "/findamember/", "mid=", "bid=", "/directory/member/"
    )

    def _is_member_detail_url(url: str) -> bool:
        u = url.lower()
        # exclude obvious non-detail routes that were showing up in your logs
        if any(bad in u for bad in ("/info", "/member/newmemberapp", "/membertomember", "/login")):
            return False
        return any(p in u for p in DETAIL_PATTERNS)


    # Replace your existing _collect_member_links with this version

    async def _collect_member_links(self, client: httpx.AsyncClient, root_url: str) -> List[str]:
        print(f"\n[START] Collecting member links from root: {root_url}")

        to_visit: List[str] = [root_url]
        seen_pages: Set[str] = set()
        member_links: Set[str] = set()

        origin = urlparse(root_url)

        def same_origin(u: str) -> bool:
            pu = urlparse(u)
            return (pu.scheme, pu.netloc) == (origin.scheme, origin.netloc)

        while to_visit:
            page = to_visit.pop(0)
            if page in seen_pages:
                continue
            seen_pages.add(page)

            try:
                resp = await self._fetch(client, page)
            except Exception as e:
                print("[SKIP] fetch failed:", page, e)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            print(f"[VISITING] {page}")

            # discover all anchors
            anchors = [urljoin(page, a.get("href", "")) for a in soup.select("a[href]")]
            # enqueue A–Z and show-all pages (THIS is the key fix)
            alpha_links = sorted({u for u in anchors if _is_alpha_or_showall(u) and same_origin(u)})
            if alpha_links:
                print(f"  [enqueue alpha/search links: {len(alpha_links)}]")
                for u in alpha_links:
                    if u not in seen_pages and u not in to_visit:
                        to_visit.append(u)

            # basic pagination discovery (rel=next, "Next", ?page=…)
            next_links = set()
            for a in soup.select("a[rel=next]"):
                h = a.get("href");  next_links.add(urljoin(page, h))
            for a in soup.find_all("a", string=re.compile(r"\bnext\b", re.I)):
                h = a.get("href");  next_links.add(urljoin(page, h))
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if re.search(r"(page|pagenum|paged|start|offset)=\d+", h, re.I):
                    next_links.add(urljoin(page, h))
            next_links = sorted({u for u in next_links if same_origin(u)})
            if next_links:
                print(f"  [enqueue pagination: {len(next_links)}]")
                for u in next_links:
                    if u not in seen_pages and u not in to_visit:
                        to_visit.append(u)

            # collect probable member detail links
            page_member_links = set(u for u in anchors if same_origin(u) and _is_member_detail_url(u))

            # fallback: card-based extraction (covers GrowthZone/ChamberMaster cards)
            if not page_member_links:
                for sel in (".mn-listing", ".gz-directory-card", ".business-listing", ".listing", ".directory-listing"):
                    for card in soup.select(sel):
                        a = card.select_one("a[href]")
                        if not a:
                            continue
                        u = urljoin(page, a.get("href", ""))
                        if same_origin(u) and _is_member_detail_url(u):
                            page_member_links.add(u)

            if page_member_links:
                print(f"  [member links on this page: {len(page_member_links)}]")
                for u in sorted(page_member_links)[:50]:  # keep console readable
                    print("    →", u)

            before = len(member_links)
            member_links |= page_member_links
            after = len(member_links)
            if after != before:
                print(f"  [total unique member links so far: {after}]")

            # also enqueue other /list/* index pages (non-detail)
            index_links = sorted({u for u in anchors if same_origin(u) and ("/list/" in u.lower()) and not _is_member_detail_url(u)})
            if index_links:
                print(f"  [enqueue other /list/* index pages: {len(index_links)}]")
                for u in index_links:
                    if u not in seen_pages and u not in to_visit:
                        to_visit.append(u)

        print(f"\n[SUMMARY] From root {root_url}: found {len(member_links)} member pages in total.")
        for link in sorted(member_links):
            print("  •", link)
        return sorted(member_links)




    async def _collect_member_links(self, client: httpx.AsyncClient, list_url: str) -> List[str]:
        print(f"\n[START] Collecting member links from root: {list_url}")

        seen_pages: Set[str] = set()
        to_visit: List[str] = [list_url]
        member_links: Set[str] = set()
        origin = urlparse(list_url).netloc

        while to_visit:
            page = to_visit.pop(0)
            print(f"\n[VISIT] {page}")
            if page in seen_pages:
                continue
            seen_pages.add(page)

            try:
                resp = await self._fetch(client, page)
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            
            print(f"[VISITING] {page}")
            # Show all <a> links discovered
            anchors = [urljoin(page, a.get("href")) for a in soup.select("a[href]")]
            print(f"   Found {len(anchors)} anchors:")
            for href in anchors[:50]:   # print first 50 to avoid flooding
                print("     ↳", href)

            # 1) Collect members from listing cards
            # Heuristics: anchors inside cards that link to company/member profiles
            for a in soup.select("a"):
                href = a.get("href")
                if not href:
                    continue
                abs_url = urljoin(page, href)
                if urlparse(abs_url).netloc != origin:
                    continue
                # Skip anchors that obviously paginate
                if any(k in abs_url.lower() for k in ["page=", "pagenum=", "paged=", "start=", "offset="]):
                    # It's a paginator link; we'll enqueue separately below
                    pass
                # Heuristic: likely member detail URLs
                if is_member_detail_url(abs_url):
                    member_links.add(abs_url)

            # 2) Discover pagination: look for 'Next' or page number links
            # Common patterns: rel='next', text 'Next', page=? etc.
            next_links = set()
            # rel=next
            for a in soup.select("a[rel=next]"):
                href = a.get("href")
                if href:
                    next_links.add(urljoin(page, href))
            # 'Next' by text
            for a in soup.find_all("a", string=re.compile(r"\bnext\b", re.I)):
                href = a.get("href")
                if href:
                    next_links.add(urljoin(page, href))
            # Numbered pages
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"(page|pagenum|paged|start|offset)=\d+", href, re.I):
                    next_links.add(urljoin(page, href))

            for nxt in sorted(next_links):
                if nxt not in seen_pages:
                    to_visit.append(nxt)

        print(f"\n[SUMMARY] From root {list_url}: found {len(member_links)} member pages in total.")
        for link in sorted(member_links):
            print("  •", link)
        return sorted(member_links)

    def _extract_text(self, node) -> str:
        return normalize_whitespace(node.get_text(" ", strip=True)) if node else ""

    def _maybe(self, soup: BeautifulSoup, selectors: List[str]) -> Optional[str]:
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return self._extract_text(node)
        return None

    def _parse_member(self, html: str, url: str) -> MemberRecord:
        soup = BeautifulSoup(html, "lxml")

        # Try typical patterns for ChamberMaster / business directories
        name = self._maybe(soup, [
            "h1", ".company-name", ".member-name", ".mn-title", ".profile h1"
        ]) or ""

        # Categories / tags
        categories = []
        for sel in [".categories", ".profile-categories", ".mn-categories", ".business-categories"]:
            node = soup.select_one(sel)
            if node:
                categories.append(self._extract_text(node))
        if not categories:
            # fallback: look for labels near 'Category'
            for label in soup.find_all(text=re.compile(r"Category", re.I)):
                parent = label.parent
                if parent:
                    categories.append(self._extract_text(parent))
        categories_text = "; ".join(sorted({c for c in categories if c}))

        # Contact info heuristics
        phone = ""
        website = ""
        email = ""
        address = ""
        city = state = postal_code = ""

        # Look for tel: links and obvious phone patterns
        for a in soup.select("a[href^='tel:']"):
            phone = a.get("href", "").replace("tel:", "").strip()
            if phone:
                break
        if not phone:
            # heuristic: find any strong/label with Phone
            for lbl in soup.find_all(text=re.compile(r"Phone", re.I)):
                t = lbl.parent.get_text(" ", strip=True) if lbl and lbl.parent else ""
                if looks_like_phone(t):
                    phone = t
                    break

        # Email
        for a in soup.select("a[href^='mailto:']"):
            email = a.get("href", "").replace("mailto:", "").strip()
            if email:
                break
        if not email:
            em = soup.find(string=re.compile(r"@"))
            if em:
                cand = self._extract_text(em.parent if hasattr(em, "parent") else soup)
                if looks_like_email(cand):
                    email = cand

        # Website
        for a in soup.select("a[href]"):
            href = a["href"]
            if href.startswith("http") and not href.startswith("mailto:") and not href.startswith("tel:"):
                # Exclude self-links / directory nav patterns
                if "facebook.com" in href or "instagram.com" in href or "twitter.com" in href or "linkedin.com" in href:
                    # Prefer the official site over socials; keep as fallback
                    if not website:
                        website = href
                else:
                    website = href
                    break

        # Address: look for address tags or recognizable blocks
        addr_candidates = []
        for sel in ["address", ".address", ".mn-address", ".company-address", ".profile-address"]:
            for n in soup.select(sel):
                txt = self._extract_text(n)
                if len(txt) > 10:
                    addr_candidates.append(txt)

        # Fallback: find likely address lines with city/state/ZIP
        if not addr_candidates:
            for n in soup.find_all(text=re.compile(r"\b[A-Z]{2}\b\s*\d{5}(?:-\d{4})?")):
                blk = self._extract_text(n.parent if hasattr(n, "parent") else soup)
                if len(blk) > 10:
                    addr_candidates.append(blk)

        if addr_candidates:
            address = addr_candidates[0]
            # Try to split into parts "Street, City, ST ZIP"
            m = re.search(r"(.+?),\s*([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)", address)
            if m:
                address, city, state, postal_code = [x.strip() for x in m.groups()]

        # Short description
        description = self._maybe(soup, [
            ".company-description", ".profile-description", ".mn-description", "meta[name='description']"
        ]) or ""
        if not description:
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                description = meta["content"].strip()

        return MemberRecord(
            source_list_url="",
            member_url=url,
            name=name,
            categories=categories_text,
            phone=phone,
            email=email,
            website=website,
            address=address,
            city=city,
            state=state,
            postal_code=postal_code,
            description=description
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _fetch_member(self, client: httpx.AsyncClient, url: str) -> Optional[MemberRecord]:
        async with self.semaphore:
            r = await client.get(url)
            r.raise_for_status()
            return self._parse_member(r.text, url)

    async def run(self) -> List[MemberRecord]:
        records: List[MemberRecord] = []
        async with self._client() as client:
            for list_url in self.urls:
                member_links = await self._collect_member_links(client, list_url)
                for u in member_links:
                    try:
                        rec = await self._fetch_member(client, u)
                        if rec:
                            rec.source_list_url = list_url
                            records.append(rec)
                    except Exception:
                        # Skip on failure; you may log this in real use
                        continue
        return records
