from __future__ import annotations

import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, field_validator


OPTIONS_PATH = Path("/data/options.json")


class Settings(BaseModel):
    check_interval_hours: int = Field(default=168, ge=1, le=168)
    scan_on_start: bool = False
    almacor_url: str = "https://almacor.com.ar/catalogo/mailing.pdf"
    caracol_home_url: str = "https://www.supercaracol.com.ar/"
    # Backward-compatible/manual fallback. Automatic discovery from caracol_home_url is preferred.
    heyzine_url: str = ""
    vision_enabled: bool = False
    vision_api_base: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    vision_api_key: str = ""
    vision_model: str = "gemini-3.6-flash"
    image_mode: str = "full"
    render_dpi: int = Field(default=170, ge=100, le=240)
    jpeg_quality: int = Field(default=88, ge=60, le=95)
    max_pages: int = Field(default=40, ge=1, le=100)
    llm_delay_seconds: float = Field(default=2.0, ge=0, le=120)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_retry_backoff_seconds: float = Field(default=5.0, ge=1, le=120)
    notify_event: bool = True

    @field_validator("vision_api_base", mode="before")
    @classmethod
    def normalize_vision_api_base(cls, value):
        value = str(value or "").strip().strip('"').strip("'")
        if not value:
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        if not re.match(r"^https?://", value, flags=re.I):
            value = "https://" + value
        return value.rstrip("/")


def load_settings() -> Settings:
    if OPTIONS_PATH.exists():
        try:
            return Settings.model_validate(json.loads(OPTIONS_PATH.read_text(encoding="utf-8")))
        except Exception:
            # Fail safe: allow the app UI/logs to come up even with malformed options.
            pass
    return Settings()
