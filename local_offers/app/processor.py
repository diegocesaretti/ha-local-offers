from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

from .config import Settings, load_settings
from . import db
from .ha import fire_catalog_event, publish_summary
from .render import render_pdf
from .sources import DownloadedCatalog, fetch_almacor, fetch_heyzine
from .vision import analyze_image, deduplicate_products

LOGGER = logging.getLogger(__name__)
CATALOG_ROOT = Path("/data/catalogs")
RENDER_ROOT = Path("/data/rendered")


class ScanManager:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.running = False
        self.last_result: dict[str, Any] | None = None

    async def scan_all(self, force: bool = False) -> dict[str, Any]:
        if self.lock.locked():
            return {"ok": False, "message": "Ya hay un escaneo en curso."}
        async with self.lock:
            self.running = True
            try:
                settings = load_settings()
                results = []
                jobs: list[tuple[str, Callable[[], Awaitable[DownloadedCatalog]]]] = [
                    ("Almacor", lambda: fetch_almacor(settings.almacor_url, CATALOG_ROOT)),
                    ("Heyzine", lambda: fetch_heyzine(settings.heyzine_url, CATALOG_ROOT)),
                ]
                for name, fetcher in jobs:
                    try:
                        results.append(await self._scan_source(name, fetcher, settings, force))
                    except Exception as exc:
                        LOGGER.exception("Error procesando %s", name)
                        results.append({"source": name, "ok": False, "error": str(exc)})
                current_stats = db.stats()
                await publish_summary(current_stats)
                result = {"ok": True, "sources": results, "stats": current_stats}
                self.last_result = result
                return result
            finally:
                self.running = False

    async def _scan_source(self, name: str, fetcher: Callable[[], Awaitable[DownloadedCatalog]],
                           settings: Settings, force: bool) -> dict[str, Any]:
        catalog = await fetcher()
        existing = db.catalog_by_hash(catalog.sha256)
        needs_processing = bool(
            existing
            and settings.vision_enabled
            and existing.get("status") != "ready"
        )
        if existing and not force and not needs_processing:
            return {
                "source": name,
                "ok": True,
                "changed": False,
                "catalog_id": existing["id"],
                "message": "Catálogo sin cambios.",
            }

        if existing and (force or needs_processing):
            catalog_id = int(existing["id"])
            db.update_catalog(catalog_id, status="processing", error=None)
        else:
            catalog_id = db.insert_catalog(
                source=catalog.source,
                source_url=catalog.source_url,
                external_id=catalog.external_id,
                title=catalog.title,
                sha256=catalog.sha256,
                pdf_path=str(catalog.pdf_path),
                page_count=catalog.page_count,
            )
            db.update_catalog(catalog_id, status="processing")

        if not settings.vision_enabled:
            db.update_catalog(catalog_id, status="downloaded")
            return {
                "source": name,
                "ok": True,
                "changed": True,
                "catalog_id": catalog_id,
                "offers": 0,
                "message": "PDF guardado; Vision desactivado.",
            }

        try:
            render_dir = RENDER_ROOT / catalog.source.lower() / catalog.sha256[:12]
            rendered = render_pdf(
                catalog.pdf_path,
                render_dir,
                settings.render_dpi,
                settings.jpeg_quality,
                settings.max_pages,
                settings.image_mode,
            )
            all_products: list[dict[str, Any]] = []
            valid_from = None
            valid_until = None

            # Sequential by design: avoids API bursts and keeps memory usage modest on a Pi.
            # A configurable pause is added between images/tiles to further protect API quotas.
            for idx, image in enumerate(rendered):
                if idx > 0 and settings.llm_delay_seconds > 0:
                    LOGGER.info("Pausa LLM de %s s antes de la siguiente imagen", settings.llm_delay_seconds)
                    await asyncio.sleep(settings.llm_delay_seconds)

                parsed = await analyze_image(image.path, image.page, image.tile, settings)
                valid_from = valid_from or parsed.get("catalog_valid_from")
                valid_until = valid_until or parsed.get("catalog_valid_until")
                all_products.extend(parsed.get("products") or [])

            all_products = deduplicate_products(all_products)
            count = db.replace_offers(catalog_id, catalog.source, all_products)
            db.update_catalog(
                catalog_id,
                valid_from=valid_from,
                valid_until=valid_until,
                status="ready",
                error=None,
            )
            if settings.notify_event:
                await fire_catalog_event({
                    "source": catalog.source,
                    "catalog_id": catalog_id,
                    "offers": count,
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                })
            return {
                "source": name,
                "ok": True,
                "changed": True,
                "catalog_id": catalog_id,
                "offers": count,
                "valid_from": valid_from,
                "valid_until": valid_until,
            }
        except Exception as exc:
            db.update_catalog(catalog_id, status="error", error=str(exc))
            raise
