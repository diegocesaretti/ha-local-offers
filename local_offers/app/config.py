from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, Field


OPTIONS_PATH = Path("/data/options.json")


class Settings(BaseModel):
    check_interval_hours: int = Field(default=12, ge=1, le=168)
    scan_on_start: bool = True
    almacor_url: str = "https://almacor.com.ar/catalogo/mailing.pdf"
    heyzine_url: str = "https://heyzine.com/flip-book/fafe2791cf.html"
    vision_enabled: bool = False
    vision_api_base: str = "https://api.openai.com/v1"
    vision_api_key: str = ""
    vision_model: str = "gpt-4.1-mini"
    image_mode: str = "full"
    render_dpi: int = Field(default=170, ge=100, le=240)
    jpeg_quality: int = Field(default=88, ge=60, le=95)
    max_pages: int = Field(default=40, ge=1, le=100)
    notify_event: bool = True


def load_settings() -> Settings:
    if OPTIONS_PATH.exists():
        try:
            return Settings.model_validate(json.loads(OPTIONS_PATH.read_text(encoding="utf-8")))
        except Exception:
            # Fail safe: allow the app UI/logs to come up even with malformed options.
            pass
    return Settings()
