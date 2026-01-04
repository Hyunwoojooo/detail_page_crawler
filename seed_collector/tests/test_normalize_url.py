from seed_collector.normalize_url import build_page_url, normalize_unknown_url


def test_normalize_unknown_url():
    url = "https://shop.example.com/product/alpha?utm_source=ad&b=2&a=1#section"
    normalized = normalize_unknown_url(url)
    assert normalized == "https://shop.example.com/product/alpha?a=1&b=2"


def test_build_page_url_replaces_param():
    url = "https://shop.example.com/list?cate_no=10&page=2"
    updated = build_page_url(url, "page", 5)
    assert updated == "https://shop.example.com/list?cate_no=10&page=5"
