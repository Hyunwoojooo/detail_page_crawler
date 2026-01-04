import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


CAFE24_DETAIL_RE = re.compile(r"/product/detail\.html", re.IGNORECASE)
CAFE24_PRODUCT_NO_RE = re.compile(r"(?:^|&|\?)product_no=\d+", re.IGNORECASE)
SHOPIFY_PRODUCT_RE = re.compile(r"/products/[^/?#]+", re.IGNORECASE)
CUSTOM_PHP_RE = re.compile(r"/detail\.php", re.IGNORECASE)
CUSTOM_PHP_ID_RE = re.compile(r"(?:^|&|\?)(pno|goodsno|product_no)=[^&]+", re.IGNORECASE)
GENERIC_PRODUCT_RE = re.compile(r"/product/([^/?#]+)", re.IGNORECASE)
GENERIC_EXCLUDE_RE = re.compile(
    r"(?:^|[-_.])(category|categories|search|board|event|editorial|collection|collections|brand|notice|policy|terms|about|member|account|login|register|join)(?:$|[-_.])",
    re.IGNORECASE,
)
GENERIC_PATH_EXCLUDE = (
    "/product/list",
    "/product/search",
    "/product/category",
    "/product/categories",
    "/product/collection",
    "/product/collections",
    "/product/board",
    "/product/brand",
)

CAFE24_LIST_SELECTORS = (
    ".xans-product-listnormal",
    ".xans-product-normalpackage",
    ".xans-product-listcategory",
)
CAFE24_EXCLUDE_ANCESTOR_HINTS = ("menu-ranking", "listmain", "swiper")


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    anchor_text: Optional[str]


def extract_product_links(html: str, base_url: str, platform_hint: str) -> List[LinkCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    return extract_product_links_from_soup(soup, base_url, platform_hint)


def extract_product_links_from_soup(
    soup: BeautifulSoup,
    base_url: str,
    platform_hint: str,
) -> List[LinkCandidate]:
    roots = _select_anchor_roots(soup, platform_hint)
    return _extract_links_from_roots(roots, base_url, platform_hint)


def extract_next_link(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    return extract_next_link_from_soup(soup, base_url)


def extract_next_link_from_soup(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    next_words = {"next", "\ub2e4\uc74c"}
    next_symbols = {">", ">>", "\u203a", "\u00bb"}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not href:
            continue
        href = href.strip()
        if _is_skippable_href(href):
            continue

        rel = [value.lower() for value in anchor.get("rel", [])]
        if "next" in rel:
            return urljoin(base_url, href)

        text = anchor.get_text(" ", strip=True).lower()
        aria = (anchor.get("aria-label") or "").lower()
        combined = f"{text} {aria}".strip()

        if any(word in combined for word in next_words):
            return urljoin(base_url, href)
        if combined in next_symbols:
            return urljoin(base_url, href)

    return None


def _select_anchor_roots(soup: BeautifulSoup, platform_hint: str) -> List[BeautifulSoup]:
    if platform_hint in ("cafe24", "auto"):
        roots = _find_cafe24_list_roots(soup)
        if roots:
            return roots
    return [soup]


def _find_cafe24_list_roots(soup: BeautifulSoup) -> List[BeautifulSoup]:
    roots: List[BeautifulSoup] = []
    for selector in CAFE24_LIST_SELECTORS:
        roots.extend(soup.select(selector))
    if roots:
        return roots

    for node in soup.find_all(class_=lambda v: v and "prdList" in v):
        if _has_ancestor_class(node, CAFE24_EXCLUDE_ANCESTOR_HINTS):
            continue
        roots.append(node)
    return roots


def _has_ancestor_class(node: BeautifulSoup, hints: tuple) -> bool:
    current = node
    while current is not None:
        classes = current.get("class", [])
        if classes:
            joined = " ".join(classes).lower()
            if any(hint in joined for hint in hints):
                return True
        current = current.parent
        if not hasattr(current, "get"):
            break
    return False


def _extract_links_from_roots(
    roots: List[BeautifulSoup],
    base_url: str,
    platform_hint: str,
) -> List[LinkCandidate]:
    seen = set()
    candidates: List[LinkCandidate] = []

    for root in roots:
        for anchor in root.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue
            href = href.strip()
            if _is_skippable_href(href):
                continue

            absolute = urljoin(base_url, href)
            matched_platform = classify_product_url(absolute)
            if not _is_allowed_platform(matched_platform, platform_hint):
                continue

            if absolute in seen:
                continue
            seen.add(absolute)

            text = anchor.get_text(" ", strip=True) or None
            candidates.append(LinkCandidate(url=absolute, anchor_text=text))

    return candidates


def classify_product_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    path = parsed.path or ""
    query = parsed.query or ""

    if CAFE24_DETAIL_RE.search(path) and CAFE24_PRODUCT_NO_RE.search(query):
        return "cafe24"
    if SHOPIFY_PRODUCT_RE.search(path):
        return "shopify"
    if CUSTOM_PHP_RE.search(path) and CUSTOM_PHP_ID_RE.search(query):
        return "custom_php"
    if _is_generic_product_detail(path):
        return "unknown"
    return None


def _is_allowed_platform(matched: Optional[str], hint: str) -> bool:
    if matched is None:
        return False
    if hint in ("auto", "unknown"):
        return True
    if matched == hint:
        return True
    if matched == "unknown":
        return True
    return False


def _is_generic_product_detail(path: str) -> bool:
    match = GENERIC_PRODUCT_RE.search(path or "")
    if not match:
        return False
    path_lower = (path or "").lower()
    if any(fragment in path_lower for fragment in GENERIC_PATH_EXCLUDE):
        return False
    slug = match.group(1)
    if not slug:
        return False
    slug_lower = slug.lower()
    if slug_lower in {"detail", "detail.html"}:
        return False
    if slug_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return False
    if GENERIC_EXCLUDE_RE.search(slug_lower):
        return False
    return True


def _is_skippable_href(href: str) -> bool:
    lower = href.lower()
    return lower.startswith("#") or lower.startswith("javascript:") or lower.startswith("mailto:") or lower.startswith("tel:")
