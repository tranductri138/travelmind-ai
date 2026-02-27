from travelmind_ai.scraping.scraping_service import clean_html


def test_clean_html_strips_scripts():
    html = "<html><body><script>alert('x')</script><p>Hello World</p></body></html>"
    result = clean_html(html)
    assert "alert" not in result
    assert "Hello World" in result


def test_clean_html_strips_styles():
    html = "<html><body><style>.x{color:red}</style><p>Content</p></body></html>"
    result = clean_html(html)
    assert "color" not in result
    assert "Content" in result


def test_clean_html_strips_nav_footer():
    html = """
    <html><body>
        <nav>Navigation</nav>
        <main><p>Main content</p></main>
        <footer>Footer</footer>
    </body></html>
    """
    result = clean_html(html)
    assert "Navigation" not in result
    assert "Footer" not in result
    assert "Main content" in result


def test_clean_html_collapses_whitespace():
    html = "<html><body><p>Line 1</p>\n\n\n\n<p>Line 2</p></body></html>"
    result = clean_html(html)
    lines = result.strip().splitlines()
    assert len(lines) == 2
