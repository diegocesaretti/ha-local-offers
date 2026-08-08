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

    # Optional secondary profile. It is tried only after the primary profile has failed.
    vision_backup_enabled: bool = False
    vision_backup_api_base: str = "https://openrouter.ai/api/v1"
    vision_backup_api_key: str = ""
    vision_backup_model: str = ""

    # Official ANMAT/INAL Listado Integrado de Alimentos Libres de Gluten (LIALG).
    anmat_enabled: bool = True
    anmat_url: str = "https://listadoalg.anmat.gob.ar/Home"
    anmat_match_threshold: float = Field(default=0.82, ge=0.65, le=1.0)
    # Reuse a recently downloaded full Excel during repeated manual scans.
    anmat_refresh_hours: int = Field(default=12, ge=1, le=168)
    # Maximum age accepted only as fallback if ANMAT cannot be reached.
    anmat_cache_days: int = Field(default=7, ge=1, le=30)
    # Kept for compatibility with existing options; the Excel importer no longer queries per brand.
    anmat_delay_seconds: float = Field(default=0.5, ge=0, le=10)
    anmat_timeout_seconds: float = Field(default=30.0, ge=5, le=120)

    image_mode: str = "full"
    render_dpi: int = Field(default=170, ge=100, le=240)
    jpeg_quality: int = Field(default=88, ge=60, le=95)
    max_pages: int = Field(default=40, ge=1, le=100)

    # Storage retention: keep historical data in SQLite, not heavy historical files.
    cleanup_enabled: bool = True
    keep_pdfs_per_source: int = Field(default=1, ge=0, le=5)

    # Shared rate-limit/retry policy for primary and backup providers.
    llm_delay_seconds: float = Field(default=2.0, ge=0, le=120)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_retry_backoff_seconds: float = Field(default=5.0, ge=1, le=120)
    notify_event: bool = True

    @field_validator("vision_api_base", "vision_backup_api_base", mode="before")
    @classmethod
    def normalize_vision_api_base(cls, value):
        value = str(value or "").strip().strip('"').strip("'")
        if not value:
            return ""
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
