from app import ha


def _base_rows():
    return [
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
            "id": 3,
            "source": "Caracol",
            "brand": "Sedal",
            "name": "Shampoo reparación",
            "presentation": "400 ml",
            "price": 3000,
            "is_food": 0,
            "deal_label": "buena",
            "history_count": 3,
        },
        {
            "id": 4,
            "source": "Caracol",
            "brand": "Whiskas",
            "name": "Alimento para gato",
            "presentation": "1 kg",
            "price": 5200,
            "is_food": 0,
            "deal_label": "nuevo_minimo",
            "history_count": 6,
        },
        {
            "id": 5,
            "source": "Almacor",
            "brand": "Marca Z",
            "name": "Vaso plástico",
            "presentation": "10 u",
            "price": 800,
            "is_food": 0,
            "deal_label": "normal",
        },
    ]


def test_meal_context_filters_food_and_compacts(monkeypatch):
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: _base_rows())
    result = ha._meal_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["name"] == "Arroz"
    assert result["offers"][0]["gluten"] == "sin_gluten"
    assert result["offers"][0]["gluten_source"] == "ANMAT"
    assert result["offers"][0]["category"] == "food"


def test_cleaning_context_detects_household_products(monkeypatch):
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: _base_rows())
    result = ha._cleaning_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["name"] == "Jabón líquido para ropa"
    assert result["offers"][0]["category"] == "cleaning"


def test_personal_care_context_excludes_cleaning(monkeypatch):
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: _base_rows())
    result = ha._personal_care_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["name"] == "Shampoo reparación"
    assert result["offers"][0]["category"] == "personal_care"


def test_pet_context_detects_pet_products(monkeypatch):
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: _base_rows())
    result = ha._pet_context()
    assert result["published_offers"] == 1
    assert result["offers"][0]["brand"] == "Whiskas"
    assert result["offers"][0]["category"] == "pet"


def test_best_deals_context_prioritizes_and_categories(monkeypatch):
    monkeypatch.setattr(ha.db, "list_offers", lambda limit=1000: _base_rows())
    result = ha._best_deals_context()
    assert result["published_offers"] == 4
    assert result["offers"][0]["brand"] == "Whiskas"
    categories = {x["category"] for x in result["offers"]}
    assert {"food", "cleaning", "personal_care", "pet"}.issubset(categories)
