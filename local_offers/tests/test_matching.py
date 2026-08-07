from app.db import _amount_signature, _match_score


def offer(brand, name, presentation):
    return {
        "brand": brand,
        "name": name,
        "variant": None,
        "presentation": presentation,
        "price": 1000,
    }


def test_volume_equivalence_liters_cc():
    a = offer("Coca Cola", "Gaseosa", "2,25 L")
    b = offer("Coca-Cola", "Gaseosa Original", "2250 cc")
    assert _amount_signature(a) == ("volume", 2250.0)
    assert _amount_signature(b) == ("volume", 2250.0)
    assert _match_score(a, b) >= 0.64


def test_different_size_is_not_match():
    a = offer("Coca Cola", "Gaseosa", "2,25 L")
    b = offer("Coca Cola", "Gaseosa", "1,5 L")
    assert _match_score(a, b) == 0.0


def test_weight_equivalence_kg_g():
    a = offer("Playadito", "Yerba mate", "1 kg")
    b = offer("Playadito", "Yerba", "1000 g")
    assert _amount_signature(a) == ("weight", 1000.0)
    assert _amount_signature(b) == ("weight", 1000.0)
    assert _match_score(a, b) >= 0.64


def test_clearly_different_brand_is_not_match():
    a = offer("Natura", "Aceite girasol", "900 ml")
    b = offer("Cocinero", "Aceite girasol", "900 ml")
    assert _match_score(a, b) == 0.0
