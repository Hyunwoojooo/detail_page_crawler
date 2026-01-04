from typing import Iterable, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


UTM_PREFIX = "utm_"


def get_shop_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_unknown_url(url: str) -> str:
    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = _remove_utm_params(query_pairs)
    sorted_pairs = sorted(filtered, key=lambda item: (item[0], item[1]))
    new_query = urlencode(sorted_pairs, doseq=True)
    normalized = parsed._replace(query=new_query, fragment="")
    return urlunparse(normalized)


def build_page_url(url: str, page_param: str, page_number: int) -> str:
    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in query_pairs if k != page_param]
    filtered.append((page_param, str(page_number)))
    new_query = urlencode(filtered, doseq=True)
    updated = parsed._replace(query=new_query, fragment="")
    return urlunparse(updated)


def _remove_utm_params(query_pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    cleaned = []
    for key, value in query_pairs:
        if key.lower().startswith(UTM_PREFIX):
            continue
        cleaned.append((key, value))
    return cleaned
