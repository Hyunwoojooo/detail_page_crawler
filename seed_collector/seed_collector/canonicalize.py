import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .normalize_url import normalize_unknown_url


CAFE24_DETAIL_RE = re.compile(r"/product/detail\.html", re.IGNORECASE)
SHOPIFY_PRODUCT_RE = re.compile(r"/products/([^/?#]+)", re.IGNORECASE)
CUSTOM_PHP_RE = re.compile(r"/detail\.php", re.IGNORECASE)
CUSTOM_PHP_ID_RE = re.compile(r"(?:^|&|\?)(pno|goodsno|product_no)=([^&]+)", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalizationResult:
    canonical_url: str
    external_product_id: Optional[str]
    platform_hint: str


def canonicalize_url(url: str, platform_hint: str) -> CanonicalizationResult:
    if platform_hint == "auto":
        detected = detect_platform(url)
        result = canonicalize_by_platform(url, detected)
        if result is not None:
            return result
        return CanonicalizationResult(normalize_unknown_url(url), None, "unknown")

    result = canonicalize_by_platform(url, platform_hint)
    if result is not None:
        return result

    fallback = detect_platform(url)
    result = canonicalize_by_platform(url, fallback)
    if result is not None:
        return result

    return CanonicalizationResult(normalize_unknown_url(url), None, "unknown")


def detect_platform(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    query = parsed.query or ""

    if CAFE24_DETAIL_RE.search(path) and "product_no=" in query:
        return "cafe24"
    if SHOPIFY_PRODUCT_RE.search(path):
        return "shopify"
    if CUSTOM_PHP_RE.search(path) and CUSTOM_PHP_ID_RE.search(query):
        return "custom_php"
    return "unknown"


def canonicalize_by_platform(url: str, platform_hint: str) -> Optional[CanonicalizationResult]:
    if platform_hint == "cafe24":
        return canonicalize_cafe24(url)
    if platform_hint == "shopify":
        return canonicalize_shopify(url)
    if platform_hint == "custom_php":
        return canonicalize_custom_php(url)
    if platform_hint == "unknown":
        return CanonicalizationResult(normalize_unknown_url(url), None, "unknown")
    return None


def canonicalize_cafe24(url: str) -> Optional[CanonicalizationResult]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    if not CAFE24_DETAIL_RE.search(parsed.path or ""):
        return None
    query = parse_qs(parsed.query)
    product_no = _first_value(query.get("product_no"))
    if not product_no:
        return None
    canonical = f"{parsed.scheme}://{parsed.netloc}/product/detail.html?product_no={product_no}"
    return CanonicalizationResult(canonical, product_no, "cafe24")


def canonicalize_shopify(url: str) -> Optional[CanonicalizationResult]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    match = SHOPIFY_PRODUCT_RE.search(parsed.path or "")
    if not match:
        return None
    handle = match.group(1)
    canonical = f"{parsed.scheme}://{parsed.netloc}/products/{handle}"
    return CanonicalizationResult(canonical, handle, "shopify")


def canonicalize_custom_php(url: str) -> Optional[CanonicalizationResult]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    if not CUSTOM_PHP_RE.search(parsed.path or ""):
        return None
    query = parse_qs(parsed.query)
    for key in ("pno", "goodsno", "product_no"):
        value = _first_value(query.get(key))
        if value:
            canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{key}={value}"
            return CanonicalizationResult(canonical, value, "custom_php")
    return None


def _first_value(values: Optional[list]) -> Optional[str]:
    if not values:
        return None
    value = values[0]
    return value if value else None
