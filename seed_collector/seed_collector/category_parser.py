import re
from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .extract_links import _is_skippable_href, classify_product_url


BREADCRUMB_HINTS = ("breadcrumb", "bread", "path", "location")
CATEGORY_CONTAINER_HINTS = ("category", "cate", "sub", "tabs", "tab", "menu", "lnb", "gnb")
ACTIVE_CLASS_HINTS = {"active", "on", "selected", "current"}
ARIA_CURRENT_HINTS = {"page", "true"}
ARIA_SELECTED_HINTS = {"true", "1"}
CATEGORY_QUERY_KEYS = {
    "cate_no",
    "category",
    "category_id",
    "cat",
    "c",
    "scate",
    "pcate",
    "mcat",
}
CATEGORY_PATH_HINTS = (
    "/product/list",
    "/category",
    "/categories",
    "/collections",
    "/collection",
    "/list",
    "/shop",
)


@dataclass(frozen=True)
class CategoryLink:
    url: str
    label: str


def extract_breadcrumbs(soup: BeautifulSoup) -> List[str]:
    containers = []

    for node in soup.find_all(attrs={"aria-label": True}):
        aria = (node.get("aria-label") or "").lower()
        if "breadcrumb" in aria:
            containers.append(node)

    containers.extend(_find_by_hint(soup, BREADCRUMB_HINTS))

    best: List[str] = []
    for container in containers:
        labels = _extract_text_nodes(container)
        if len(labels) > len(best):
            best = labels

    cleaned = [_clean_text(label) for label in best]
    cleaned = [label for label in cleaned if label and label.lower() not in {"home", "main"}]
    return _dedupe_preserve_order(cleaned)


def extract_subcategory_links(soup: BeautifulSoup, base_url: str) -> List[CategoryLink]:
    containers = _find_by_hint(soup, CATEGORY_CONTAINER_HINTS)
    if not containers:
        containers = [soup]

    base_host = urlparse(base_url).netloc.lower()
    candidates: List[CategoryLink] = []
    seen = set()

    for container in containers:
        for anchor in container.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue
            href = href.strip()
            if _is_skippable_href(href):
                continue
            label = _clean_text(anchor.get_text(" ", strip=True))
            if not label:
                continue

            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.netloc.lower() != base_host:
                continue
            if classify_product_url(absolute) is not None:
                continue
            if not _looks_like_category_url(absolute):
                continue

            normalized = _strip_fragment(absolute)
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(CategoryLink(url=normalized, label=label))

    return candidates


def detect_active_subcategory_label(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    containers = _find_by_hint(soup, CATEGORY_CONTAINER_HINTS)
    if not containers:
        containers = [soup]

    base_host = urlparse(base_url).netloc.lower()

    for container in containers:
        for anchor in container.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue
            href = href.strip()
            if _is_skippable_href(href):
                continue

            label = _clean_text(anchor.get_text(" ", strip=True))
            if not label:
                continue

            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.netloc.lower() != base_host:
                continue
            if classify_product_url(absolute) is not None:
                continue
            if not _looks_like_category_url(absolute):
                continue

            if _is_active_anchor(anchor):
                return label

    return None


def _looks_like_category_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    query = parse_qs(parsed.query)

    if any(key in query for key in CATEGORY_QUERY_KEYS):
        return True
    return any(hint in path for hint in CATEGORY_PATH_HINTS)


def _find_by_hint(soup: BeautifulSoup, hints: Iterable[str]) -> List[BeautifulSoup]:
    hits = []
    for node in soup.find_all(True):
        classes = " ".join(node.get("class", [])).lower()
        node_id = (node.get("id") or "").lower()
        if any(hint in classes or hint in node_id for hint in hints):
            hits.append(node)
    return hits


def _is_active_anchor(anchor: BeautifulSoup) -> bool:
    aria_current = (anchor.get("aria-current") or "").lower()
    if aria_current in ARIA_CURRENT_HINTS:
        return True

    aria_selected = (anchor.get("aria-selected") or "").lower()
    if aria_selected in ARIA_SELECTED_HINTS:
        return True

    if _has_active_class(anchor):
        return True
    if anchor.parent and _has_active_class(anchor.parent):
        return True
    if anchor.parent and anchor.parent.parent and _has_active_class(anchor.parent.parent):
        return True

    return False


def _has_active_class(node: BeautifulSoup) -> bool:
    classes = node.get("class", [])
    for name in classes:
        if name.lower() in ACTIVE_CLASS_HINTS:
            return True
    return False


def _extract_text_nodes(container: BeautifulSoup) -> List[str]:
    labels: List[str] = []
    for node in container.find_all(["a", "span", "li"]):
        text = node.get_text(" ", strip=True)
        if text:
            labels.append(text)
    return labels


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\\s+", " ", text or "").strip()
    cleaned = cleaned.strip(">/|")
    return cleaned


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _strip_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))
