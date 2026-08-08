from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .vision import _call_with_failover, _extract_json


GLUTEN_SYSTEM_PROMPT = """Sos un clasificador conservador de alimentos para una app de ofertas de supermercados argentinos.
Recibís una lista de productos YA extraídos del catálogo como texto. No recibís imágenes ni ingredientes completos.
Tu tarea es estimar el estado respecto de gluten/TACC usando únicamente el nombre, marca, variante y presentación disponibles.

Estados permitidos:
- sin_gluten: sólo cuando el texto lo indica explícitamente (SIN TACC, sin gluten, gluten free) o cuando existe alta certeza sobre el producto exacto y su condición libre de gluten.
- con_tacc: cuando el producto/categoría contiene o normalmente se elabora con trigo, avena, cebada o centeno, o el producto exacto es conocido por contener gluten.
- indeterminado: cuando faltan datos, hay variantes posibles, formulaciones que pueden cambiar, riesgo de contaminación cruzada o no podés afirmarlo con alta certeza.

Reglas:
- Preferí indeterminado antes que adivinar.
- No conviertas una categoría naturalmente sin gluten en una certificación del envase.
- No cambies los IDs ni nombres recibidos.
- confidence debe estar entre 0 y 1.
- La clasificación es orientativa y NO reemplaza la etiqueta/envase ni registros oficiales.

Respondé exactamente con JSON:
{"results":[{"id":123,"status":"sin_gluten|con_tacc|indeterminado","confidence":0.0}]}
Incluí todos los IDs recibidos.
"""


def _product_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(k) or "").strip()
        for k in ("brand", "name", "variant", "presentation")
        if str(item.get(k) or "").strip()
    )


def _payload(offers: list[dict[str, Any]]) -> dict[str, Any]:
    products = [
        {"id": int(item["id"]), "product": _product_text(item)}
        for item in offers
    ]
    return {
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": GLUTEN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Clasificá estos productos:\n" + json.dumps(products, ensure_ascii=False),
            },
        ],
    }


def _normalize_results(parsed: dict[str, Any], offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_ids = {int(item["id"]) for item in offers}
    rows = parsed.get("results")
    if not isinstance(rows, list):
        raise RuntimeError("Clasificación gluten: results no es una lista.")

    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    valid_status = {"sin_gluten", "con_tacc", "indeterminado"}

    for row in rows:
        try:
            oid = int(row.get("id"))
        except Exception:
            continue
        if oid not in allowed_ids or oid in seen:
            continue
        status = str(row.get("status") or "indeterminado").strip().lower()
        if status not in valid_status:
            status = "indeterminado"
        try:
            confidence = max(0.0, min(float(row.get("confidence") or 0.0), 1.0))
        except Exception:
            confidence = 0.0
        normalized.append({"id": oid, "status": status, "confidence": confidence})
        seen.add(oid)

    for oid in sorted(allowed_ids - seen):
        normalized.append({"id": oid, "status": "indeterminado", "confidence": 0.0})
    return normalized


async def classify_gluten_text(offers: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """Classify already-scraped food products using text only, with the normal LLM failover chain."""
    food = [item for item in offers if item.get("is_food") in (1, True)]
    if not food:
        return {"results": [], "provider_used": None, "provider_model": None}

    content, profile = await _call_with_failover(_payload(food), settings, timeout=120)
    parsed = _extract_json(content)
    return {
        "results": _normalize_results(parsed, food),
        "provider_used": profile.name,
        "provider_model": profile.model,
    }
