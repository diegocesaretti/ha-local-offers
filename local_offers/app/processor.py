from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

from .config import Settings, load_settings
from . import checkpoints, db
from .ha import fire_catalog_event, publish_summary
from .render import RenderedImage, render_pdf
from .sources import DownloadedCatalog, fetch_almacor, fetch_caracol
from .vision import analyze_image, deduplicate_products, verify_sin_tacc_image

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
                    (
                        "Caracol",
                        lambda: fetch_caracol(
                            settings.caracol_home_url,
                            settings.heyzine_url,
                            CATALOG_ROOT,
                        ),
                    ),
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
        pending_sin_tacc = bool(
            existing
            and existing.get("status") == "ready"
            and settings.vision_enabled
            and db.get_state(self._tacc_complete_key(int(existing["id"]))) != "1"
        )

        if existing and not force and not needs_processing:
            if pending_sin_tacc:
                catalog_id = int(existing["id"])
                mode = self._stored_image_mode(catalog_id, settings.image_mode)
                rendered = self._render(catalog, settings, mode)
                tacc = await self._verify_sin_tacc(catalog_id, rendered, settings, reset=False)
                return {
                    "source": name,
                    "ok": True,
                    "changed": False,
                    "catalog_id": catalog_id,
                    "message": "Catálogo sin cambios; se continuó la verificación SIN TACC pendiente.",
                    "source_url": catalog.source_url,
                    "sin_tacc": tacc,
                }
            return {
                "source": name,
                "ok": True,
                "changed": False,
                "catalog_id": existing["id"],
                "message": "Catálogo sin cambios.",
                "source_url": catalog.source_url,
            }

        if existing and (force or needs_processing):
            catalog_id = int(existing["id"])
            db.update_catalog(
                catalog_id,
                status="processing",
                error=None,
                title=catalog.title,
                source_url=catalog.source_url,
                source=catalog.source,
            )
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

        if force:
            checkpoints.clear_catalog(catalog.sha256)
            self._clear_tacc_state(catalog_id)

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
            rendered = self._render(catalog, settings, settings.image_mode)
            all_products: list[dict[str, Any]] = []
            valid_from = None
            valid_until = None
            provider_usage = {"primary": 0, "backup": 0}
            reused = 0
            processed = 0

            for image in rendered:
                parsed = None if force else checkpoints.load_chunk(
                    catalog.sha256, image.page, image.tile
                )
                if parsed is not None:
                    reused += 1
                    LOGGER.info(
                        "Checkpoint reutilizado %s p%s/%s",
                        catalog.source, image.page, image.tile,
                    )
                else:
                    parsed = await analyze_image(image.path, image.page, image.tile, settings)
                    checkpoints.save_chunk(catalog.sha256, image.page, image.tile, parsed)
                    processed += 1

                valid_from = valid_from or parsed.get("catalog_valid_from")
                valid_until = valid_until or parsed.get("catalog_valid_until")
                provider = parsed.get("provider_used")
                if provider in provider_usage:
                    provider_usage[provider] += 1
                all_products.extend(parsed.get("products") or [])

            all_products = deduplicate_products(all_products)
            count = db.replace_offers(catalog_id, catalog.source, all_products)
            db.update_catalog(
                catalog_id,
                valid_from=valid_from,
                valid_until=valid_until,
                status="ready",
                error=None,
                source_url=catalog.source_url,
                source=catalog.source,
            )

            # Prices/products are now safely in SQLite. SIN TACC is intentionally a second pass.
            self._clear_tacc_state(catalog_id)
            tacc = await self._verify_sin_tacc(catalog_id, rendered, settings, reset=False)
            history_updated = db.refresh_history_metrics(catalog.source)

            if settings.notify_event:
                await fire_catalog_event({
                    "source": catalog.source,
                    "catalog_id": catalog_id,
                    "offers": count,
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                    "provider_usage": provider_usage,
                    "checkpoint_reused": reused,
                    "sin_tacc_complete": tacc.get("complete", False),
                })
            return {
                "source": name,
                "ok": True,
                "changed": True,
                "catalog_id": catalog_id,
                "offers": count,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "source_url": catalog.source_url,
                "provider_usage": provider_usage,
                "checkpoint_reused": reused,
                "chunks_processed_now": processed,
                "chunks_total": len(rendered),
                "history_metrics_updated": history_updated,
                "sin_tacc": tacc,
            }
        except Exception as exc:
            db.update_catalog(catalog_id, status="error", error=str(exc))
            saved = checkpoints.count_chunks(catalog.sha256)
            LOGGER.error(
                "Escaneo interrumpido en %s; %s páginas/recortes quedan checkpointados para continuar.",
                catalog.source, saved,
            )
            raise

    def _render(self, catalog: DownloadedCatalog, settings: Settings, image_mode: str) -> list[RenderedImage]:
        render_dir = RENDER_ROOT / catalog.source.lower() / catalog.sha256[:12]
        return render_pdf(
            catalog.pdf_path,
            render_dir,
            settings.render_dpi,
            settings.jpeg_quality,
            settings.max_pages,
            image_mode,
        )

    @staticmethod
    def _tacc_complete_key(catalog_id: int) -> str:
        return f"sin_tacc_complete:{catalog_id}"

    @staticmethod
    def _tacc_chunk_key(catalog_id: int, page: int, tile: str) -> str:
        return f"sin_tacc_chunk:{catalog_id}:{int(page)}:{tile}"

    def _clear_tacc_state(self, catalog_id: int) -> None:
        with db.connect() as conn:
            conn.execute(
                "DELETE FROM app_state WHERE key=? OR key LIKE ?",
                (self._tacc_complete_key(catalog_id), f"sin_tacc_chunk:{catalog_id}:%"),
            )
            conn.execute("UPDATE offers SET sin_tacc=NULL WHERE catalog_id=?", (catalog_id,))

    def _stored_image_mode(self, catalog_id: int, fallback: str) -> str:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT raw_json FROM offers WHERE catalog_id=? LIMIT 2000", (catalog_id,)
            ).fetchall()
        for row in rows:
            try:
                raw = json.loads(row[0] or "{}")
                if str(raw.get("tile") or "").startswith("q"):
                    return "quarters"
            except Exception:
                continue
        return fallback if fallback in {"full", "quarters"} else "full"

    def _offers_for_image(self, catalog_id: int, page: int, tile: str) -> list[dict[str, Any]]:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM offers WHERE catalog_id=? AND page=? AND is_food=1 ORDER BY id",
                (catalog_id, int(page)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                raw = json.loads(item.get("raw_json") or "{}")
            except Exception:
                raw = {}
            stored_tile = str(raw.get("tile") or "full")
            if stored_tile != str(tile):
                continue
            out.append(item)
        return out

    async def _verify_sin_tacc(self, catalog_id: int, rendered: list[RenderedImage],
                               settings: Settings, reset: bool = False) -> dict[str, Any]:
        if reset:
            self._clear_tacc_state(catalog_id)
        verified_chunks = 0
        reused_chunks = 0
        products_checked = 0
        errors: list[str] = []
        provider_usage = {"primary": 0, "backup": 0}

        for image in rendered:
            state_key = self._tacc_chunk_key(catalog_id, image.page, image.tile)
            if db.get_state(state_key) == "1":
                reused_chunks += 1
                continue

            offers = self._offers_for_image(catalog_id, image.page, image.tile)
            if not offers:
                db.set_state(state_key, "1")
                verified_chunks += 1
                continue

            try:
                result = await verify_sin_tacc_image(image.path, offers, settings)
                provider = result.get("provider_used")
                if provider in provider_usage:
                    provider_usage[provider] += 1
                rows = result.get("results") or []
                with db.connect() as conn:
                    for row in rows:
                        value = row.get("sin_tacc")
                        db_value = None if value is None else (1 if value else 0)
                        conn.execute(
                            "UPDATE offers SET sin_tacc=? WHERE id=? AND catalog_id=?",
                            (db_value, int(row["id"]), catalog_id),
                        )
                        products_checked += 1
                db.set_state(state_key, "1")
                verified_chunks += 1
            except Exception as exc:
                message = f"p{image.page}/{image.tile}: {exc}"
                errors.append(message)
                LOGGER.warning("SIN TACC pendiente %s catálogo %s: %s", image.tile, catalog_id, exc)
                # Do not fail the catalog: products/prices are already safely stored.

        complete = not errors
        db.set_state(self._tacc_complete_key(catalog_id), "1" if complete else "0")
        return {
            "complete": complete,
            "verified_chunks": verified_chunks,
            "checkpoint_reused": reused_chunks,
            "products_checked": products_checked,
            "provider_usage": provider_usage,
            "errors": errors[:10],
        }
