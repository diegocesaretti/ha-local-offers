from app import ha


def test_meal_context_filters_food_and_compacts(monkeypatch):
    rows = [
        {
            "id": 1,
            "source": "Caracol",
            "brand": "Marca A",
            "name": "Arroz",
            "variant": None,
            "presentation": "1 kg",
            "price": 1200,
            "previous_price": 1500,
            "promotion_text": "Oferta",
            "is_food": 1,
            "sin_tacc": 1,
            "gluten_source": "ANMAT",
            "deal_label": "muy_buena",
            "change_vs_avg_30": -15.0,
            "historical_min": 1100,
            "history_count": 4,
        },
        {
            "id": 2,
            "source": "Almacor",
            "brand": "Marca B",
            "name": "Detergente limón",
            "presentation": "750 ml",
            "price": 999,
            "is_food": 0,
            "deal_label": "buena",
        },
    ]
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: rows)
    result = ha._meal_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["name"] == "Arroz"
    assert result["offers"][0]["gluten"] == "sin_gluten"
    assert result["offers"][0]["gluten_source"] == "ANMAT"


def test_cleaning_context_detects_household_products(monkeypatch):
    rows = [
        {
            "id": 10,
            "source": "Caracol",
            "brand": "Ala",
            "name": "Jabón líquido para ropa",
            "variant": "Matic",
            "presentation": "3 L",
            "price": 4500,
            "promotion_text": "20% off",
            "is_food": 0,
            "deal_label": "buena",
            "history_count": 2,
        },
        {
            "id": 11,
            "source": "Caracol",
            "brand": "Marca X",
            "name": "Shampoo",
            "presentation": "400 ml",
            "price": 3000,
            "is_food": 0,
            "deal_label": "buena",
        },
        {
            "id": 12,
            "source": "Almacor",
            "brand": "Marca Y",
            "name": "Fideos",
            "presentation": "500 g",
            "price": 900,
            "is_food": 1,
            "deal_label": "muy_buena",
        },
    ]
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: rows)
    result = ha._cleaning_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["name"] == "Jabón líquido para ropa"
