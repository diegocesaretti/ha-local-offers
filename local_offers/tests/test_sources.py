from app.sources import extract_heyzine_info, sha256_bytes


def test_extract_heyzine_info():
    html = '''<script>
    var flipbookcfg = {"id":"fafe2791cf","name":"v3/demo.pdf","title":"04.08 al 17.08","num_pages":12}; var other = {};
    </script>'''
    info = extract_heyzine_info(html, "https://heyzine.com/flip-book/fafe2791cf.html")
    assert info["id"] == "fafe2791cf"
    assert info["pdf_filename"] == "v3/demo.pdf"
    assert info["title"] == "04.08 al 17.08"
    assert info["pdf_urls"][1].endswith("/files/uploaded/v3/demo.pdf")


def test_sha256():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
