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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("local_offers")
manager = ScanManager()
STATIC = Path(__file__).parent / "static"


async def scheduler_loop() -> None:
    # Reload options before every interval so changing App options only requires restart for immediate effect,
    # but future intervals still honor the persisted value.
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


app = FastAPI(title="Ofertas Locales", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def ingress_only(request: Request, call_next):
    # Home Assistant Ingress proxy is 172.30.32.2. Loopback is allowed for local smoke tests.
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
        "config": {
            "check_interval_hours": settings.check_interval_hours,
            "vision_enabled": settings.vision_enabled,
            "vision_model": settings.vision_model,
            "image_mode": settings.image_mode,
            "almacor_url": settings.almacor_url,
            "heyzine_url": settings.heyzine_url,
            "api_key_configured": bool(settings.vision_api_key),
        },
    }


@app.post("/api/scan")
async def scan(force: bool = Query(False)):
    return await manager.scan_all(force=force)


@app.get("/api/offers")
async def offers(source: str | None = None, q: str | None = None, limit: int = Query(300, ge=1, le=1000)):
    return {"items": db.list_offers(source=source, query=q, limit=limit)}


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
