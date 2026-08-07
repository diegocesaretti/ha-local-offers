from app.vision import _extract_json, deduplicate_products


def test_extract_json_fenced():
    data = _extract_json('```json\n{"products": []}\n```')
    assert data == {"products": []}


def test_dedupe_tiles():
    items = [
        {"page": 1, "brand": "X", "name": "Yerba", "presentation": "1 kg", "price": 1000, "promotion_text": None},
        {"page": 1, "brand": "X", "name": "Yerba", "presentation": "1 kg", "price": 1000, "promotion_text": None},
    ]
    assert len(deduplicate_products(items)) == 1
