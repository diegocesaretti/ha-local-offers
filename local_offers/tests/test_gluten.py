from app.gluten import _normalize_results


def test_gluten_status_normalization_and_missing_ids():
    offers = [
        {"id": 10, "is_food": 1},
        {"id": 11, "is_food": 1},
        {"id": 12, "is_food": 1},
    ]
    parsed = {
        "results": [
            {"id": 10, "status": "sin_gluten", "confidence": 1.2},
            {"id": 11, "status": "con_tacc", "confidence": 0.9},
            {"id": 999, "status": "sin_gluten", "confidence": 1},
        ]
    }
    rows = {row["id"]: row for row in _normalize_results(parsed, offers)}
    assert rows[10] == {"id": 10, "status": "sin_gluten", "confidence": 1.0}
    assert rows[11]["status"] == "con_tacc"
    assert rows[12] == {"id": 12, "status": "indeterminado", "confidence": 0.0}
    assert 999 not in rows


def test_unknown_status_becomes_indeterminate():
    offers = [{"id": 1, "is_food": 1}]
    rows = _normalize_results({"results": [{"id": 1, "status": "maybe", "confidence": 0.5}]}, offers)
    assert rows[0]["status"] == "indeterminado"
