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
PERSONAL_CARE_CONTEXT_LIMIT = 20
PET_CONTEXT_LIMIT = 15
BEST_DEALS_CONTEXT_LIMIT = 25

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
    "jabon liquido ropa", "jabon liquido para ropa", "jabon para ropa", "jabon en polvo", "polvo para lavar",
    "suavizante", "quitamanchas", "blanqueador", "apresto", "perfume para ropa",
    "esponja", "virulana", "lana de acero", "rejilla", "trapo", "paño", "pano",
    "bolsa de residuos", "bolsas de residuos", "bolsa basura", "bolsas basura",
    "rollo cocina", "papel cocina", "toalla de papel", "servilleta", "papel higienico",
    "insecticida", "repelente de insectos", "pastilla mosquitos", "aerosol mosquitos",
    "limpiamuebles", "lustramuebles", "cera piso", "destapacañerias", "destapacanerias",
}

PERSONAL_CARE_KEYWORDS = {
    "shampoo", "acondicionador", "crema enjuague", "jabon tocador", "jabon corporal",
    "gel de ducha", "desodorante", "antitranspirante", "pasta dental", "dentifrico",
    "cepillo dental", "enjuague bucal", "hilo dental", "afeitadora", "maquina afeitar",
    "espuma afeitar", "gel afeitar", "crema corporal", "crema manos", "protector solar",
    "toallitas femeninas", "tampon", "pañal", "panal", "toallitas humedas", "algodon",
    "hisopo", "alcohol en gel", "pañuelo descartable", "panuelo descartable",
}

PET_KEYWORDS = {
    "alimento gato", "alimento para gato", "comida gato", "comida para gato", "cat chow",
    "whiskas", "gati", "excellent gato", "purina gato", "sobre gato", "pouch gato",
    "alimento perro", "alimento para perro", "comida perro", "comida para perro", "dog chow",
    "pedigree", "excellent perro", "purina perro", "sobre perro", "pouch perro",
    "arena gato", "arena sanitaria", "piedritas gato", "piedras sanitarias", "snack mascota",
    "snack perro", "snack gato", "premio perro", "premio gato",
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


def _compact_offer(item: dict[str, Any], include_gluten: bool = False, category: str | None = None) -> dict[str, Any]:
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
    if category:
        compact["category"] = category
    if include_gluten:
        compact["gluten"] = _gluten_status(item)
        compact["gluten_source"] = item.get("gluten_source")
    return compact


def _text(item: dict[str, Any]) -> str:
    return _norm(" ".join(str(item.get(k) or "") for k in ("brand", "name", "variant", "presentation", "promotion_text")))


def _has_keyword(item: dict[str, Any], keywords: set[str]) -> bool:
    text = _text(item)
    return bool(text) and any(_norm(keyword) in text for keyword in keywords)


def _meal_context(limit: int = MEAL_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [item for item in db.list_offers(limit=1000) if item.get("is_food") in (1, True) and item.get("price") is not None]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item, include_gluten=True, category="food") for item in items[:max(1, int(limit))]]
    return {"offers": compact, "total_food_offers": len(items), "published_offers": len(compact)}


def _cleaning_context(limit: int = CLEANING_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [
        item for item in db.list_offers(limit=1000)
        if item.get("price") is not None and item.get("is_food") not in (1, True) and _has_keyword(item, CLEANING_KEYWORDS)
    ]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item, category="cleaning") for item in items[:max(1, int(limit))]]
    return {"offers": compact, "total_cleaning_offers": len(items), "published_offers": len(compact)}


def _personal_care_context(limit: int = PERSONAL_CARE_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [
        item for item in db.list_offers(limit=1000)
        if item.get("price") is not None
        and item.get("is_food") not in (1, True)
        and not _has_keyword(item, CLEANING_KEYWORDS)
        and _has_keyword(item, PERSONAL_CARE_KEYWORDS)
    ]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item, category="personal_care") for item in items[:max(1, int(limit))]]
    return {"offers": compact, "total_personal_care_offers": len(items), "published_offers": len(compact)}


def _pet_context(limit: int = PET_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [item for item in db.list_offers(limit=1000) if item.get("price") is not None and _has_keyword(item, PET_KEYWORDS)]
    items.sort(key=_sort_key, reverse=True)
    compact = [_compact_offer(item, category="pet") for item in items[:max(1, int(limit))]]
    return {"offers": compact, "total_pet_offers": len(items), "published_offers": len(compact)}


def _best_deals_context(limit: int = BEST_DEALS_CONTEXT_LIMIT) -> dict[str, Any]:
    items = [
        item for item in db.list_offers(limit=1000)
        if item.get("price") is not None and item.get("deal_label") in {"nuevo_minimo", "minimo_historico", "muy_buena", "buena"}
    ]
    items.sort(key=_sort_key, reverse=True)
    compact = []
    for item in items[:max(1, int(limit))]:
        if item.get("is_food") in (1, True):
            category = "food"
        elif _has_keyword(item, PET_KEYWORDS):
            category = "pet"
        elif _has_keyword(item, CLEANING_KEYWORDS):
            category = "cleaning"
        elif _has_keyword(item, PERSONAL_CARE_KEYWORDS):
            category = "personal_care"
        else:
            category = "other"
        compact.append(_compact_offer(item, include_gluten=(category == "food"), category=category))
    return {"offers": compact, "total_good_deals": len(items), "published_offers": len(compact)}


async def _post_state(client: httpx.AsyncClient, headers: dict[str, str], entity_id: str, payload: dict[str, Any]) -> None:
    response = await client.post(f"{CORE_API}/states/{entity_id}", headers=headers, json=payload)
    response.raise_for_status()


def _context_payload(friendly_name: str, icon: str, context: dict[str, Any], stats: dict[str, Any], total_key: str, note: str) -> dict[str, Any]:
    return {
        "state": str(context["published_offers"]),
        "attributes": {
            "friendly_name": friendly_name,
            "icon": icon,
            "unit_of_measurement": "productos",
            "offers": context["offers"],
            "published_offers": context["published_offers"],
            total_key: context.get(total_key, 0),
            "last_update": stats.get("last_update"),
            "note": note,
        },
    }


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
    cleaning = _cleaning_context()
    personal = _personal_care_context()
    pet = _pet_context()
    best = _best_deals_context()

    payloads = (
        ("sensor.local_offers", summary_payload),
        ("sensor.local_offers_meal_context", _context_payload(
            "Ofertas Locales - Contexto Cocina", "mdi:food-variant", meal, stats, "total_food_offers",
            "Ofertas alimentarias compactas para recetas y sugerencias de comida.",
        )),
        ("sensor.local_offers_cleaning_context", _context_payload(
            "Ofertas Locales - Contexto Limpieza", "mdi:spray-bottle", cleaning, stats, "total_cleaning_offers",
            "Ofertas compactas de limpieza, lavadero y hogar.",
        )),
        ("sensor.local_offers_personal_care_context", _context_payload(
            "Ofertas Locales - Contexto Cuidado Personal", "mdi:shower-head", personal, stats, "total_personal_care_offers",
            "Ofertas compactas de higiene y cuidado personal.",
        )),
        ("sensor.local_offers_pet_context", _context_payload(
            "Ofertas Locales - Contexto Mascotas", "mdi:paw", pet, stats, "total_pet_offers",
            "Ofertas compactas de alimento, snacks y productos para mascotas.",
        )),
        ("sensor.local_offers_best_deals_context", _context_payload(
            "Ofertas Locales - Mejores Oportunidades", "mdi:fire", best, stats, "total_good_deals",
            "Mejores oportunidades actuales de cualquier categoría, priorizadas por histórico y promociones.",
        )),
    )

    async with httpx.AsyncClient(timeout=15) as client:
        for entity_id, payload in payloads:
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
            response = await client.post(f"{CORE_API}/events/local_offers_catalog_updated", headers=headers, json=data)
            response.raise_for_status()
        except Exception as exc:
            LOGGER.warning("No se pudo disparar evento en Home Assistant: %s", exc)
