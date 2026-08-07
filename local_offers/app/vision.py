from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sos un extractor de ofertas de folletos de supermercados argentinos.
Tu única tarea es leer con precisión la imagen y devolver JSON válido. No inventes.
Cada precio debe asociarse al producto visualmente correspondiente. Conservá promociones como 2x1,
2da unidad, descuento con tarjeta, precio por kg, etc. Si un dato no es legible usá null.
Los precios argentinos pueden usar punto como separador de miles: $ 3.499 significa 3499.
No hagas cálculos de descuentos: sólo extraé lo impreso.

Respondé exactamente con este objeto:
{
  "catalog_valid_from": "YYYY-MM-DD o null",
  "catalog_valid_until": "YYYY-MM-DD o null",
  "products": [
    {
      "brand": "string o null",
      "name": "string",
      "variant": "string o null",
      "presentation": "string o null",
      "price": 0.0,
      "previous_price": 0.0,
      "promotion_text": "string o null",
      "confidence": 0.0
    }
  ]
}
confidence debe estar entre 0 y 1. Omití elementos decorativos que no sean productos ofertados.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _vision_endpoint(settings: Settings) -> str:
    base = str(settings.vision_api_base or "").strip().strip('"').strip("'")
    if not base:
        raise RuntimeError("vision_api_base está vacío.")
    if not re.match(r"^https?://", base, flags=re.I):
        base = "https://" + base

    # Gemini OpenAI compatibility: accept either the base URL or the full
    # /chat/completions URL and always normalize to Google's canonical endpoint.
    if "generativelanguage.googleapis.com" in base.lower():
        return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    base = re.sub(r"/chat/completions/?$", "", base, flags=re.I).rstrip("/")
    endpoint = base + "/chat/completions"
    if not re.match(r"^https?://", endpoint, flags=re.I):
        raise RuntimeError(f"vision_api_base inválido: {settings.vision_api_base!r}")
    return endpoint


async def analyze_image(path: Path, page: int, tile: str, settings: Settings) -> dict[str, Any]:
    if not settings.vision_enabled:
        return {"catalog_valid_from": None, "catalog_valid_until": None, "products": []}
    if not settings.vision_api_key:
        raise RuntimeError("Vision está activado pero vision_api_key está vacío.")

    endpoint = _vision_endpoint(settings)
    headers = {
        "Authorization": f"Bearer {settings.vision_api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in str(settings.vision_api_base):
        headers["HTTP-Referer"] = "https://www.home-assistant.io/"
        headers["X-Title"] = "Home Assistant - Ofertas Locales"

    user_text = (
        f"Página {page}, recorte {tile}. Extraé todos los productos y ofertas visibles. "
        f"Año actual de referencia: {datetime.now().year}. Si la vigencia muestra sólo día/mes y es "
        "claramente el catálogo actual, usá ese año; si hay duda dejá la fecha en null."
    )
    payload = {
        "model": settings.vision_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": _data_uri(path), "detail": "high"}},
                ],
            },
        ],
    }

    LOGGER.info("Vision request -> %s | model=%s | page=%s | tile=%s", endpoint, settings.vision_model, page, tile)

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        if response.status_code == 400 and "response_format" in response.text.lower():
            fallback = dict(payload)
            fallback.pop("response_format", None)
            response = await client.post(endpoint, headers=headers, json=fallback)
        if response.status_code >= 400:
            body = response.text[:1000]
            hint = ""
            if response.status_code == 404 and "generativelanguage.googleapis.com" in endpoint:
                hint = (
                    " Verificá vision_model y que tu clave pertenezca a Gemini API/Google AI Studio. "
                    "Endpoint usado: " + endpoint
                )
            raise RuntimeError(f"Vision API devolvió HTTP {response.status_code}: {body}{hint}")
        data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    except Exception as exc:
        raise RuntimeError(f"Respuesta Vision inesperada: {str(data)[:1000]}") from exc
    parsed = _extract_json(content)
    products = parsed.get("products") or []
    for item in products:
        item["page"] = page
        item["tile"] = tile
    return parsed


def deduplicate_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conservative dedupe for overlapping quarter tiles."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for item in products:
        key = (
            int(item.get("page") or 0),
            str(item.get("brand") or "").strip().lower(),
            str(item.get("name") or "").strip().lower(),
            str(item.get("presentation") or "").strip().lower(),
            item.get("price"),
            str(item.get("promotion_text") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
