from app.config import Settings
from app.vision import _extract_json, _vision_endpoint, deduplicate_products


def test_extract_json_fenced():
    data = _extract_json('```json\n{"products": []}\n```')
    assert data == {"products": []}


def test_dedupe_tiles():
    items = [
        {"page": 1, "brand": "X", "name": "Yerba", "presentation": "1 kg", "price": 1000, "promotion_text": None},
        {"page": 1, "brand": "X", "name": "Yerba", "presentation": "1 kg", "price": 1000, "promotion_text": None},
    ]
    assert len(deduplicate_products(items)) == 1


def test_gemini_endpoint_adds_https():
    settings = Settings(vision_api_base="generativelanguage.googleapis.com/v1beta/openai")
    assert settings.vision_api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert _vision_endpoint(settings) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def test_default_settings_are_gemini_weekly_and_paced():
    settings = Settings()
    assert settings.check_interval_hours == 168
    assert settings.vision_api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert settings.vision_model == "gemini-3.6-flash"
    assert settings.llm_delay_seconds == 2
    assert settings.llm_max_retries == 3
    assert settings.llm_retry_backoff_seconds == 5
