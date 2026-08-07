from datetime import datetime, timezone

from app.db import _amount_signature, _compute_price_metrics, _match_score


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


def test_historical_new_minimum():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    observations = [
        {"price": 1200, "catalog_created_at": "2026-07-31T12:00:00+00:00"},
        {"price": 1150, "catalog_created_at": "2026-07-20T12:00:00+00:00"},
        {"price": 1250, "catalog_created_at": "2026-06-15T12:00:00+00:00"},
    ]
    metrics = _compute_price_metrics(1000, observations, now)
    assert metrics["history_count"] == 3
    assert metrics["historical_min"] == 1150
    assert metrics["deal_label"] == "nuevo_minimo"
    assert metrics["change_vs_avg_30"] < 0


def test_historical_above_average():
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    observations = [
        {"price": 1000, "catalog_created_at": "2026-08-01T12:00:00+00:00"},
        {"price": 1050, "catalog_created_at": "2026-07-25T12:00:00+00:00"},
    ]
    metrics = _compute_price_metrics(1200, observations, now)
    assert metrics["deal_label"] == "por_encima"
    assert metrics["change_vs_avg_30"] > 5
