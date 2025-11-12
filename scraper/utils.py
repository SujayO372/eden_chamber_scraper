import re
from urllib.parse import urljoin, urlparse

def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def looks_like_phone(text: str) -> bool:
    return bool(re.search(r"(\+?\d[\d\s().-]{6,})", text or ""))

def looks_like_email(text: str) -> bool:
    return bool(re.search(r"\b[\w.\-]+@[\w\-]+(?:\.[A-Za-z]{2,})+\b", text or ""))

def is_member_detail_url(href: str) -> bool:
    # Heuristic for ChamberMaster-style member detail pages
    # Common patterns include '/member/' or '/list/...' leading to a detail page
    # We'll allow anything under the same origin that's not a pagination link
    # and contains 'member' or 'info' or 'listing' keywords.
    return any(k in href.lower() for k in ["member", "info", "listing", "Profile", "profile"])
