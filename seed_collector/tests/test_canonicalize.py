from seed_collector.canonicalize import canonicalize_url


def test_cafe24_canonicalization():
    url = "https://shop.example.com/product/detail.html?product_no=123&cate_no=9"
    result = canonicalize_url(url, "auto")
    assert result.platform_hint == "cafe24"
    assert result.external_product_id == "123"
    assert result.canonical_url == "https://shop.example.com/product/detail.html?product_no=123"


def test_shopify_canonicalization():
    url = "https://shop.example.com/products/sample-tee?variant=1&utm_source=ad"
    result = canonicalize_url(url, "auto")
    assert result.platform_hint == "shopify"
    assert result.external_product_id == "sample-tee"
    assert result.canonical_url == "https://shop.example.com/products/sample-tee"


def test_custom_php_canonicalization():
    url = "https://shop.example.com/detail.php?goodsno=999&ref=1"
    result = canonicalize_url(url, "auto")
    assert result.platform_hint == "custom_php"
    assert result.external_product_id == "999"
    assert result.canonical_url == "https://shop.example.com/detail.php?goodsno=999"


def test_unknown_canonicalization():
    url = "https://shop.example.com/product/alpha?utm_source=ad&b=2&a=1#section"
    result = canonicalize_url(url, "auto")
    assert result.platform_hint == "unknown"
    assert result.external_product_id is None
    assert result.canonical_url == "https://shop.example.com/product/alpha?a=1&b=2"
