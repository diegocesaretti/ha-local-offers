from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any

import httpx

from . import db

LOGGER = logging.getLogger(__name__)
CORE_API = "http://supervisor/core/api"
MEAL_CONTEXT_LIMIT = 25
CLEANING_CONTEXT_LIMIT = 20

DEAL_RANK = {
    "nuevo_minimo": 7,
    "minimo_historico": 6,
    "muy_buena": 5,
    "buena": 4,
    "normal": 2,
    "sin_historial": 1,
    "por_encima": 0,
    None: 1,
}

CLEANING_KEYWORDS = {
    "detergente", "lavandina", "lejia", "desinfectante", "limpiador", "limpieza",
    "limpiapisos", "limpia pisos", "limpiavidrios", "limpia vidrios", "desengrasante",
    "jabon liquido ropa", "jabon para ropa", "jabon en polvo", "polvo para lavar",
    "suavizante", "quitamanchas", "blanqueador", "apresto", "perfume para ropa",
    "esponja", "virulana", "lana de acero", "rejilla", "trapo", "paño", "pano",
    "bolsa de residuos", "bolsas de residuos", "bolsa basura", "bolsas basura",
    "rollo cocina", "papel cocina", "toalla de papel", "servilleta", "papel higienico",
    "insecticida", "repelente de insectos", "pastilla mosquitos", "aerosol mosquitos",
    "limpiamuebles", "lustramuebles", "cera piso", "destapacañerias", "destapacanerias",
}


def _headers() -> dict[str, str] | None:
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _gluten_status(item: dict[str, Any]) -> str:
    value = item.get("sin_tacc")
    if value in (1, True):
        return "sin_gluten"
    if value in (0, False):
        return "con_tacc"
    return "indeterminado"


def _sort_key(item: dict[str, Any]):
    promo_bonus = 1 if str(item.get("promotion_text") or "").strip() else 0
    previous_bonus = 1 if item.get("previous_price") else 0
    delta = item.get("change_vs_avg_30")
    if delta is None:
        delta = item.get("change_vs_avg_60")
    if delta is None:
        delta = item.get("change_vs_avg_90")
    delta = float(delta) if delta is not None else 999.0
    return (
        DEAL_RANK.get(item.get("deal_label"), 1),
        promo_bonus,
        previous_bonus,
        -delta,
        item.get("history_count") or 0,
    )


def _compact_offer(item: dict[str, Any], include_gluten: bool = False) -> dict[str, Any]:
    compact = {
        "id": item.get("id"),
        "store": item.get("source"),
        "brand": item.get("brand"),
        "name": item.get("name"),
        "variant": item.get("variant"),
        "presentation": item.get("presentation"),
        "price": item.get("price"),
        "previous_price": item.get("previous_price"),
        "promotion": item.get("promotion_text"),
        "deal": item.get("deal_label"),
        "change_vs_avg_30": item.get("change_vs_avg_30"),
        "historical_min": item.get("historical_min"),
    }
    if include_gluten:
        compact["gluten"] = _gluten_status(item)
        compact["gluten_source"] = item.get("gluten_source")
    return compact


def _meal_context(limit: int = MEAL_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [
        item for item in db.list_offers(limit=1000)
        if item.get("is_food") in (1, True) and item.get("price") is not None
    ]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item, include_gluten=True) for item in items[:max(1, int(limit))]]
    return {
        "offers": compact,
        "total_food_offers": len(items),
        "published_offers": len(compact),
    }


def _is_cleaning_offer(item: dict[str, Any]) -> bool:
    if item.get("is_food") in (1, True):
        return False
    text = _norm(" ".join(str(item.get(k) or "") for k in ("brand", "name", "variant", "presentation", "promotion_text")))
    if not text:
        return False
    return any(_norm(keyword) in text for keyword in CLEANING_KEYWORDS)


def _cleaning_context(limit: int = CLEANING_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [
        item for item in db.list_offers(limit=1000)
        if item.get("price") is not None and _is_cleaning_offer(item)
    ]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item) for item in items[:max(1, int(limit))]]
    return {
        "offers": compact,
        "total_cleaning_offers": len(items),
        "published_offers": len(compact),
    }


async def _post_state(client: httpx.AsyncClient, headers: dict[str, str], entity_id: str, payload: dict[str, Any]) -> None:
    response = await client.post(
        f"{CORE_API}/states/{entity_id}",
        headers=headers,
        json=payload,
    )
    response.raise_for_status()


async def publish_summary(stats: dict[str, Any]) -> None:
    headers = _headers()
    if not headers:
        LOGGER.info("SUPERVISOR_TOKEN no disponible; omitiendo sensores de Home Assistant.")
        return

    summary_payload = {
        "state": str(stats.get("offers", 0)),
        "attributes": {
            "friendly_name": "Ofertas Locales",
            "icon": "mdi:tag-multiple",
            "catalogs": stats.get("catalogs", 0),
            "by_source": stats.get("by_source", {}),
            "last_update": stats.get("last_update"),
            "unit_of_measurement": "ofertas",
        },
    }

    meal = _meal_context()
    meal_payload = {
        "state": str(meal["published_offers"]),
        "attributes": {
            "friendly_name": "Ofertas Locales - Contexto Cocina",
            "icon": "mdi:food-variant",
            "unit_of_measurement": "productos",
            "offers": meal["offers"],
            "published_offers": meal["published_offers"],
            "total_food_offers": meal["total_food_offers"],
            "last_update": stats.get("last_update"),
            "note": "Lista compacta para automatizaciones/LLM; el listado completo permanece en el Add-on.",
        },
    }

    cleaning = _cleaning_context()
    cleaning_payload = {
        "state": str(cleaning["published_offers"]),
        "attributes": {
            "friendly_name": "Ofertas Locales - Contexto Limpieza",
            "icon": "mdi:spray-bottle",
            "unit_of_measurement": "productos",
            "offers": cleaning["offers"],
            "published_offers": cleaning["published_offers"],
            "total_cleaning_offers": cleaning["total_cleaning_offers"],
            "last_update": stats.get("last_update"),
            "note": "Lista compacta de limpieza/lavadero/hogar para automatizaciones/LLM.",
        },
    }

    async with httpx.AsyncClient(timeout=15) as client:
        for entity_id, payload in (
            ("sensor.local_offers", summary_payload),
            ("sensor.local_offers_meal_context", meal_payload),
            ("sensor.local_offers_cleaning_context", cleaning_payload),
        ):
            try:
                await _post_state(client, headers, entity_id, payload)
            except Exception as exc:
                LOGGER.warning("No se pudo publicar %s: %s", entity_id, exc)


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
