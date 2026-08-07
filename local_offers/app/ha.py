from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
CORE_API = "http://supervisor/core/api"


def _headers() -> dict[str, str] | None:
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def publish_summary(stats: dict[str, Any]) -> None:
    headers = _headers()
    if not headers:
        LOGGER.info("SUPERVISOR_TOKEN no disponible; omitiendo sensor de Home Assistant.")
        return
    state = str(stats.get("offers", 0))
    payload = {
        "state": state,
        "attributes": {
            "friendly_name": "Ofertas Locales",
            "icon": "mdi:tag-multiple",
            "catalogs": stats.get("catalogs", 0),
            "by_source": stats.get("by_source", {}),
            "last_update": stats.get("last_update"),
            "unit_of_measurement": "ofertas",
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.post(
                f"{CORE_API}/states/sensor.local_offers",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except Exception as exc:
            LOGGER.warning("No se pudo publicar sensor.local_offers: %s", exc)


async def fire_catalog_event(data: dict[str, Any]) -> None:
    headers = _headers()
    if not headers:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.post(
                f"{CORE_API}/events/local_offers_catalog_updated",
                headers=headers,
                json=data,
            )
            response.raise_for_status()
        except Exception as exc:
            LOGGER.warning("No se pudo disparar evento en Home Assistant: %s", exc)
