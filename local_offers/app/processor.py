from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import checkpoints, db
from .anmat_excel import get_dataset, match_products_anmat_excel
from .config import Settings, load_settings
from .gluten import classify_gluten_text
from .ha import fire_catalog_event, publish_summary
from .render import RenderedImage, render_pdf
from .sources import DownloadedCatalog, fetch_almacor, fetch_caracol
from .storage import cleanup_storage
from .vision import analyze_image, deduplicate_products

LOGGER = logging.getLogger(__name__)
CATALOG_ROOT = Path("/data/catalogs")
RENDER_ROOT = Path("/data/rendered")
GLUTEN_BATCH_SIZE = 50


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
            settings = load_settings()
            try:
                self._ensure_gluten_columns()

                # Refresh the complete official ANMAT Excel once per survey. Repeated manual
                # scans inside anmat_refresh_hours reuse the current local copy.
                anmat_dataset = await get_dataset(settings, force=False)
                anmat_summary = {k: v for k, v in anmat_dataset.items() if k != "rows"}
                if anmat_dataset.get("rows") is not None:
                    anmat_summary["rows"] = len(anmat_dataset.get("rows") or [])

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

                cleanup = cleanup_storage(settings)
                current_stats = db.stats()
                await publish_summary(current_stats)
                result = {
                    "ok": True,
                    "sources": results,
                    "stats": current_stats,
                    "anmat": anmat_summary,
                    "cleanup": cleanup,
                }
                self.last_result = result
                return result
            finally:
                self.running = False

    async def _scan_source(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[DownloadedCatalog]],
        settings: Settings,
        force: bool,
    ) -> dict[str, Any]:
        catalog = await fetcher()
        existing = db.catalog_by_hash(catalog.sha256)
        gluten_state = (
            db.get_state(self._gluten_complete_key(int(existing["id"])))
            if existing else None
        )
        needs_processing = bool(
            existing
            and settings.vision_enabled
            and existing.get("status") != "ready"
        )
        pending_gluten = bool(
            existing
            and existing.get("status") == "ready"
            and settings.vision_enabled
            and gluten_state != "1"
        )

        if existing and not force and not needs_processing:
            if pending_gluten:
                catalog_id = int(existing["id"])
                gluten = await self._classify_gluten(
                    catalog_id,
                    settings,
                    reset=(gluten_state is None),
                )
                return {
                    "source": name,
                    "ok": True,
                    "changed": False,
                    "catalog_id": catalog_id,
                    "message": "Catálogo sin cambios; se continuó la clasificación gluten pendiente.",
                    "source_url": catalog.source_url,
                    "gluten": gluten,
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
            self._clear_gluten_state(catalog_id)

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
                        catalog.source,
                        image.page,
                        image.tile,
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

            # Extraction succeeded: the page checkpoints are now redundant because SQLite
            # contains the complete product list. Gluten classification is text-only.
            checkpoints.clear_catalog(catalog.sha256)

            self._clear_gluten_state(catalog_id)
            gluten = await self._classify_gluten(catalog_id, settings, reset=False)
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
                    "gluten_complete": gluten.get("complete", False),
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
                "gluten": gluten,
            }
        except Exception as exc:
            db.update_catalog(catalog_id, status="error", error=str(exc))
            saved = checkpoints.count_chunks(catalog.sha256)
            LOGGER.error(
                "Escaneo interrumpido en %s; %s páginas/recortes quedan checkpointados para continuar.",
                catalog.source,
                saved,
            )
            raise

    def _render(
        self,
        catalog: DownloadedCatalog,
        settings: Settings,
        image_mode: str,
    ) -> list[RenderedImage]:
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
    def _gluten_complete_key(catalog_id: int) -> str:
        return f"gluten_text_complete:{catalog_id}"

    @staticmethod
    def _gluten_offer_key(catalog_id: int, offer_id: int) -> str:
        return f"gluten_text_offer:{catalog_id}:{offer_id}"

    @staticmethod
    def _ensure_gluten_columns() -> None:
        with db.connect() as conn:
            names = {row[1] for row in conn.execute("PRAGMA table_info(offers)").fetchall()}
            additions = {
                "gluten_source": "TEXT",
                "gluten_confidence": "REAL",
                "gluten_detail": "TEXT",
            }
            for name, definition in additions.items():
                if name not in names:
                    conn.execute(f"ALTER TABLE offers ADD COLUMN {name} {definition}")

    def _clear_gluten_state(self, catalog_id: int) -> None:
        self._ensure_gluten_columns()
        with db.connect() as conn:
            conn.execute(
                "DELETE FROM app_state WHERE key=? OR key LIKE ? OR key LIKE ?",
                (
                    self._gluten_complete_key(catalog_id),
                    f"gluten_text_offer:{catalog_id}:%",
                    f"sin_tacc_chunk:{catalog_id}:%",
                ),
            )
            conn.execute(
                "DELETE FROM app_state WHERE key=?",
                (f"sin_tacc_complete:{catalog_id}",),
            )
            conn.execute(
                "UPDATE offers SET sin_tacc=NULL, gluten_source=NULL, gluten_confidence=NULL, gluten_detail=NULL "
                "WHERE catalog_id=?",
                (catalog_id,),
            )

    def _pending_food_offers(self, catalog_id: int) -> tuple[list[dict[str, Any]], int]:
        self._ensure_gluten_columns()
        with db.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM offers WHERE catalog_id=? AND is_food=1 ORDER BY id",
                    (catalog_id,),
                ).fetchall()
            ]
        pending: list[dict[str, Any]] = []
        reused = 0
        for item in rows:
            key = self._gluten_offer_key(catalog_id, int(item["id"]))
            if db.get_state(key) == "1":
                reused += 1
            else:
                pending.append(item)
        return pending, reused

    def _save_gluten_result(
        self,
        catalog_id: int,
        offer_id: int,
        status: str,
        source: str,
        confidence: float | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if status == "sin_gluten":
            db_value = 1
        elif status == "con_tacc":
            db_value = 0
        else:
            db_value = None
        with db.connect() as conn:
            conn.execute(
                "UPDATE offers SET sin_tacc=?, gluten_source=?, gluten_confidence=?, gluten_detail=? "
                "WHERE id=? AND catalog_id=?",
                (
                    db_value,
                    source,
                    confidence,
                    json.dumps(detail or {}, ensure_ascii=False),
                    offer_id,
                    catalog_id,
                ),
            )
            conn.execute(
                "INSERT INTO app_state(key,value) VALUES(?, '1') "
                "ON CONFLICT(key) DO UPDATE SET value='1'",
                (self._gluten_offer_key(catalog_id, offer_id),),
            )

    def _collapse_gluten_checkpoints(self, catalog_id: int) -> None:
        with db.connect() as conn:
            conn.execute(
                "DELETE FROM app_state WHERE key LIKE ?",
                (f"gluten_text_offer:{catalog_id}:%",),
            )

    async def _classify_gluten(
        self,
        catalog_id: int,
        settings: Settings,
        reset: bool = False,
    ) -> dict[str, Any]:
        if reset:
            self._clear_gluten_state(catalog_id)

        pending, reused_products = self._pending_food_offers(catalog_id)
        if not pending:
            db.set_state(self._gluten_complete_key(catalog_id), "1")
            self._collapse_gluten_checkpoints(catalog_id)
            return {
                "complete": True,
                "products_checked": 0,
                "checkpoint_reused": reused_products,
                "anmat_matches": 0,
                "batches_processed": 0,
                "provider_usage": {"primary": 0, "backup": 0},
                "errors": [],
            }

        products_checked = 0
        batches_processed = 0
        provider_usage = {"primary": 0, "backup": 0}
        errors: list[str] = []

        # 1) Official LIALG complete Excel: only strong, unambiguous Vigente matches become green ANMAT.
        anmat = await match_products_anmat_excel(pending, settings)
        for oid, match in (anmat.get("matches") or {}).items():
            self._save_gluten_result(
                catalog_id,
                int(oid),
                "sin_gluten",
                "ANMAT",
                float(match.get("score") or 0.0),
                match,
            )
            products_checked += 1

        errors.extend(f"ANMAT: {x}" for x in (anmat.get("errors") or []))

        # 2) Everything ANMAT could not resolve is classified from already-scraped text.
        pending, _ = self._pending_food_offers(catalog_id)
        for offset in range(0, len(pending), GLUTEN_BATCH_SIZE):
            batch = pending[offset:offset + GLUTEN_BATCH_SIZE]
            try:
                result = await classify_gluten_text(batch, settings)
                provider = result.get("provider_used")
                if provider in provider_usage:
                    provider_usage[provider] += 1

                for row in result.get("results") or []:
                    self._save_gluten_result(
                        catalog_id,
                        int(row["id"]),
                        str(row.get("status") or "indeterminado"),
                        "LLM",
                        float(row.get("confidence") or 0.0),
                        {
                            "provider": provider,
                            "model": result.get("provider_model"),
                        },
                    )
                    products_checked += 1
                batches_processed += 1
            except Exception as exc:
                message = f"LLM lote {offset // GLUTEN_BATCH_SIZE + 1}: {exc}"
                errors.append(message)
                LOGGER.warning("Clasificación gluten pendiente catálogo %s: %s", catalog_id, exc)
                break

        remaining, total_reused = self._pending_food_offers(catalog_id)
        complete = not remaining
        db.set_state(self._gluten_complete_key(catalog_id), "1" if complete else "0")
        if complete:
            self._collapse_gluten_checkpoints(catalog_id)
        return {
            "complete": complete,
            "products_checked": products_checked,
            "checkpoint_reused": total_reused,
            "anmat_matches": len(anmat.get("matches") or {}),
            "anmat_dataset_rows": anmat.get("dataset_rows", 0),
            "anmat_dataset_kind": anmat.get("dataset_kind"),
            "anmat_dataset_cached": anmat.get("dataset_cached"),
            "anmat_dataset_age_hours": anmat.get("dataset_age_hours"),
            "batches_processed": batches_processed,
            "batch_size": GLUTEN_BATCH_SIZE,
            "remaining": len(remaining),
            "provider_usage": provider_usage,
            "errors": errors[:10],
        }
