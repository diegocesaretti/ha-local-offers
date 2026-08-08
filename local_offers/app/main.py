from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, HTMLResponse

from . import db
from .config import load_settings
from .processor import ScanManager
from .vision import get_llm_metrics, test_vision_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("local_offers")
manager = ScanManager()
STATIC = Path(__file__).parent / "static"


async def scheduler_loop() -> None:
    while True:
        settings = load_settings()
        await asyncio.sleep(settings.check_interval_hours * 3600)
        try:
            await manager.scan_all(force=False)
        except Exception:
            LOGGER.exception("Falló el escaneo programado")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        updated = db.refresh_history_metrics()
        LOGGER.info("Métricas históricas actualizadas al iniciar: %s ofertas", updated)
    except Exception:
        LOGGER.exception("No se pudieron recalcular métricas históricas al iniciar")
    scheduler = asyncio.create_task(scheduler_loop())
    settings = load_settings()
    startup_task = None
    if settings.scan_on_start:
        startup_task = asyncio.create_task(manager.scan_all(force=False))
    try:
        yield
    finally:
        scheduler.cancel()
        if startup_task and not startup_task.done():
            startup_task.cancel()


app = FastAPI(title="Ofertas Locales", version="0.3.1", lifespan=lifespan)


@app.middleware("http")
async def ingress_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in {"172.30.32.2", "127.0.0.1", "::1"}:
        return JSONResponse(status_code=403, content={"detail": "Ingress only"})
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/api/status")
async def status():
    settings = load_settings()
    return {
        "running": manager.running,
        "stats": db.stats(),
        "catalogs": db.latest_catalogs(10),
        "last_result": manager.last_result,
        "llm_metrics": get_llm_metrics(),
        "config": {
            "check_interval_hours": settings.check_interval_hours,
            "vision_enabled": settings.vision_enabled,
            "vision_api_base": settings.vision_api_base,
            "vision_model": settings.vision_model,
            "vision_backup_enabled": settings.vision_backup_enabled,
            "vision_backup_api_base": settings.vision_backup_api_base,
            "vision_backup_model": settings.vision_backup_model,
            "image_mode": settings.image_mode,
            "almacor_url": settings.almacor_url,
            "caracol_home_url": settings.caracol_home_url,
            "heyzine_url": settings.heyzine_url,
            "anmat_enabled": settings.anmat_enabled,
            "anmat_url": settings.anmat_url,
            "anmat_match_threshold": settings.anmat_match_threshold,
            "anmat_cache_days": settings.anmat_cache_days,
            "api_key_configured": bool(settings.vision_api_key),
            "backup_api_key_configured": bool(settings.vision_backup_api_key),
            "llm_delay_seconds": settings.llm_delay_seconds,
            "llm_max_retries": settings.llm_max_retries,
            "llm_retry_backoff_seconds": settings.llm_retry_backoff_seconds,
        },
    }


@app.post("/api/test-vision")
async def test_vision():
    settings = load_settings()
    try:
        return await test_vision_api(settings)
    except Exception as exc:
        LOGGER.exception("Falló la prueba de API LLM")
        return {"ok": False, "error": str(exc)}


@app.post("/api/scan")
async def scan(force: bool = Query(False)):
    return await manager.scan_all(force=force)


@app.get("/api/offers")
async def offers(source: str | None = None, q: str | None = None, limit: int = Query(300, ge=1, le=1000)):
    return {"items": db.list_offers(source=source, query=q, limit=limit)}


@app.get("/api/compare")
async def compare(q: str | None = None, limit: int = Query(300, ge=1, le=1000)):
    return {"items": db.compare_current_offers(query=q, limit=limit)}


@app.get("/api/deals")
async def deals(q: str | None = None, limit: int = Query(300, ge=1, le=1000)):
    return {"items": db.best_deals(query=q, limit=limit)}


@app.get("/api/history/{offer_id}")
async def offer_history(offer_id: int, limit: int = Query(50, ge=1, le=200)):
    result = db.price_history_for_offer(offer_id, limit=limit)
    if not result:
        raise HTTPException(404, "Oferta no encontrada")
    return result


@app.get("/api/catalogs")
async def catalogs(limit: int = Query(20, ge=1, le=100)):
    return {"items": db.latest_catalogs(limit)}


@app.get("/api/catalog/{catalog_id}/pdf")
async def catalog_pdf(catalog_id: int):
    catalog = db.get_catalog(catalog_id)
    if not catalog:
        raise HTTPException(404, "Catálogo no encontrado")
    path = Path(catalog["pdf_path"])
    if not path.exists():
        raise HTTPException(404, "PDF no disponible")
    return FileResponse(path, media_type="application/pdf", filename=f"catalog-{catalog_id}.pdf")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8099, log_level="info")
