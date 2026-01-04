from seed_collector.extract_links import extract_next_link, extract_product_links


def test_extract_product_links_dedupes_and_absolutizes():
    html = """
    <html>
      <body>
        <a href="/product/detail.html?product_no=123">Product A</a>
        <a href="/product/detail.html?product_no=123">Duplicate</a>
        <a href="https://shop.example.com/products/hat">Hat</a>
        <a href="/detail.php?pno=555">Custom</a>
        <a href="/product/alpha">Generic</a>
        <a href="/product/list-woman.html?cate_no=2074">List</a>
      </body>
    </html>
    """
    base_url = "https://shop.example.com/list?page=1"
    links = extract_product_links(html, base_url, "auto")
    urls = {link.url for link in links}

    assert "https://shop.example.com/product/detail.html?product_no=123" in urls
    assert "https://shop.example.com/products/hat" in urls
    assert "https://shop.example.com/detail.php?pno=555" in urls
    assert "https://shop.example.com/product/alpha" in urls
    assert "https://shop.example.com/product/list-woman.html?cate_no=2074" not in urls
    assert len(urls) == 4


def test_extract_next_link():
    html = """
    <html>
      <body>
        <a href="/list?page=1">1</a>
        <a href="/list?page=2" rel="next">Next</a>
      </body>
    </html>
    """
    base_url = "https://shop.example.com/list?page=1"
    next_link = extract_next_link(html, base_url)
    assert next_link == "https://shop.example.com/list?page=2"
