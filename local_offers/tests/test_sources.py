from app.sources import discover_caracol_catalog_url, extract_heyzine_info, sha256_bytes


def test_extract_heyzine_info():
    html = '''<script>
    var flipbookcfg = {"id":"fafe2791cf","name":"v3/demo.pdf","title":"04.08 al 17.08","num_pages":12}; var other = {};
    </script>'''
    info = extract_heyzine_info(html, "https://heyzine.com/flip-book/fafe2791cf.html")
    assert info["id"] == "fafe2791cf"
    assert info["pdf_filename"] == "v3/demo.pdf"
    assert info["title"] == "04.08 al 17.08"
    assert info["pdf_urls"][1].endswith("/files/uploaded/v3/demo.pdf")


def test_discover_caracol_catalog_strips_tracking():
    html = '''
    <a class="catalogo" href="https://heyzine.com/flip-book/fafe2791cf.html?fbclid=tracking">Catálogo</a>
    '''
    assert discover_caracol_catalog_url(html) == "https://heyzine.com/flip-book/fafe2791cf.html"


def test_discover_caracol_catalog_handles_html_entities():
    html = '''
    <a href="https://heyzine.com/flip-book/abc123.html?x=1&amp;y=2">Ver ofertas</a>
    '''
    assert discover_caracol_catalog_url(html) == "https://heyzine.com/flip-book/abc123.html"


def test_sha256():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
