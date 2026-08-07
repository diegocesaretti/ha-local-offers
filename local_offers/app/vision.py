from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import db
from .config import Settings

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sos un extractor de ofertas de folletos de supermercados argentinos.
Tu única tarea es leer con precisión la imagen y devolver JSON válido. No inventes.
Cada precio debe asociarse al producto visualmente correspondiente. Conservá promociones como 2x1,
2da unidad, descuento con tarjeta, precio por kg, etc. Si un dato no es legible usá null.
Los precios argentinos pueden usar punto como separador de miles: $ 3.499 significa 3499.
No hagas cálculos de descuentos: sólo extraé lo impreso.

Clasificá también si cada producto es alimento o bebida usando is_food.
NO determines SIN TACC en esta etapa: la verificación de gluten se hace después, sobre la base de datos ya armada.

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
      "is_food": true,
      "confidence": 0.0
    }
  ]
}
confidence debe estar entre 0 y 1. Omití elementos decorativos que no sean productos ofertados.
"""

SIN_TACC_SYSTEM_PROMPT = """Sos un verificador visual de evidencia SIN TACC en folletos argentinos.
Recibís una imagen del folleto y una lista de productos YA extraídos de la base de datos, cada uno con un ID.
Tu única tarea es decidir si JUNTO A ESE PRODUCTO se ve evidencia explícita sobre gluten.

Reglas estrictas:
- true SOLO si se ve claramente logo/texto SIN TACC o una declaración inequívoca de libre de gluten asociada a ese producto.
- false SOLO si se ve una declaración inequívoca de que NO es apto / contiene gluten asociada a ese producto.
- null si no se ve evidencia suficiente, el logo es ambiguo, está lejos del producto o no podés asociarlo con seguridad.
- Nunca uses conocimiento de marca, ingredientes habituales ni supongas que un alimento naturalmente sin gluten es apto.
- No cambies nombre, precio ni clasificación del producto.

Respondé exactamente:
{"results":[{"id":123,"sin_tacc":true}]}
Incluí todos los IDs recibidos; usá null cuando no haya evidencia.
"""

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
TEST_IMAGE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAdklEQVR4nO3aQQqAMAwAQSP+/8v16lVEhsLOvZClp0BmrXXs7NQDfFWAVoBWgFaAVoBWgFaAdr19MDN/zPH0akXZ/gcK0ArQCtAK0ArQCtAK0ArQCtAK0ArQCtAK0ArQCtC2D5gOnrACtAK0ArQCtAK0ArTtA25PQAl7UMir8gAAAABJRU5ErkJggg=="
)

_LLM_REQUEST_LOCK = asyncio.Lock()
_LAST_LLM_REQUEST_AT = 0.0
_METRICS_STATE_KEY = "llm_metrics_v1"


@dataclass(frozen=True)
class VisionProfile:
    name: str
    enabled: bool
    api_base: str
    api_key: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_base and self.api_key and self.model)


def _primary_profile(settings: Settings) -> VisionProfile:
    return VisionProfile("primary", True, settings.vision_api_base, settings.vision_api_key, settings.vision_model)


def _backup_profile(settings: Settings) -> VisionProfile:
    return VisionProfile(
        "backup",
        settings.vision_backup_enabled,
        settings.vision_backup_api_base,
        settings.vision_backup_api_key,
        settings.vision_backup_model,
    )


def _default_metrics() -> dict[str, Any]:
    return {
        "primary_success_count": 0,
        "primary_failure_count": 0,
        "backup_success_count": 0,
        "backup_failure_count": 0,
        "failover_count": 0,
        "last_provider_used": None,
        "last_success_at": None,
        "last_failover_at": None,
        "last_primary_error": None,
        "last_backup_error": None,
    }


def get_llm_metrics() -> dict[str, Any]:
    metrics = _default_metrics()
    raw = db.get_state(_METRICS_STATE_KEY)
    if raw:
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                metrics.update(stored)
        except Exception:
            LOGGER.warning("No se pudieron leer las métricas LLM persistidas")
    return metrics


def _save_metrics(metrics: dict[str, Any]) -> None:
    db.set_state(_METRICS_STATE_KEY, json.dumps(metrics, ensure_ascii=False))


def _record_provider_result(profile_name: str, success: bool, error: str | None = None) -> None:
    metrics = get_llm_metrics()
    now = datetime.now(timezone.utc).isoformat()
    if profile_name == "backup":
        key = "backup_success_count" if success else "backup_failure_count"
        metrics[key] = int(metrics.get(key) or 0) + 1
        metrics["last_backup_error"] = None if success else (error or "Error desconocido")[:800]
    else:
        key = "primary_success_count" if success else "primary_failure_count"
        metrics[key] = int(metrics.get(key) or 0) + 1
        metrics["last_primary_error"] = None if success else (error or "Error desconocido")[:800]
    if success:
        metrics["last_provider_used"] = profile_name
        metrics["last_success_at"] = now
    _save_metrics(metrics)


def _record_failover() -> None:
    metrics = get_llm_metrics()
    metrics["failover_count"] = int(metrics.get("failover_count") or 0) + 1
    metrics["last_failover_at"] = datetime.now(timezone.utc).isoformat()
    _save_metrics(metrics)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _endpoint_from_base(api_base: str) -> str:
    base = str(api_base or "").strip().strip('"').strip("'")
    if not base:
        raise RuntimeError("URL base de Vision vacía.")
    if not re.match(r"^https?://", base, flags=re.I):
        base = "https://" + base
    if "generativelanguage.googleapis.com" in base.lower():
        return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    base = re.sub(r"/chat/completions/?$", "", base, flags=re.I).rstrip("/")
    return base + "/chat/completions"


def _vision_endpoint(value: Settings | str) -> str:
    if isinstance(value, Settings):
        return _endpoint_from_base(value.vision_api_base)
    return _endpoint_from_base(str(value))


def _headers(profile: VisionProfile) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}
    if "openrouter.ai" in profile.api_base.lower():
        headers["HTTP-Referer"] = "https://www.home-assistant.io/"
        headers["X-Title"] = "Home Assistant - Ofertas Locales"
    return headers


def _retry_fallback_seconds(attempt: int, base: float) -> float:
    """Wait before retry N. Retry 1=base, retry 2=2*base, retry 3=60s, then 120/240..."""
    if attempt < 2:
        return float(base) * (2 ** attempt)
    return min(60.0 * (2 ** (attempt - 2)), 300.0)


def _retry_after_seconds(response: httpx.Response, fallback: float) -> float:
    value = response.headers.get("Retry-After")
    if value:
        try:
            # Never retry sooner than our local policy; respect a longer server request.
            return max(fallback, min(float(value), 300.0))
        except ValueError:
            pass
    return fallback


async def _rate_limited_post(client: httpx.AsyncClient, endpoint: str, headers: dict[str, str],
                             payload: dict[str, Any], delay_seconds: float) -> httpx.Response:
    global _LAST_LLM_REQUEST_AT
    async with _LLM_REQUEST_LOCK:
        now = time.monotonic()
        wait = max(0.0, float(delay_seconds) - (now - _LAST_LLM_REQUEST_AT))
        if wait:
            await asyncio.sleep(wait)
        try:
            return await client.post(endpoint, headers=headers, json=payload)
        finally:
            _LAST_LLM_REQUEST_AT = time.monotonic()


async def _post_with_retries(client: httpx.AsyncClient, endpoint: str, headers: dict[str, str],
                             payload: dict[str, Any], settings: Settings) -> httpx.Response:
    current_payload = payload
    for attempt in range(settings.llm_max_retries + 1):
        response = await _rate_limited_post(client, endpoint, headers, current_payload, settings.llm_delay_seconds)
        if response.status_code == 400 and "response_format" in response.text.lower() and "response_format" in current_payload:
            current_payload = dict(current_payload)
            current_payload.pop("response_format", None)
            response = await _rate_limited_post(client, endpoint, headers, current_payload, settings.llm_delay_seconds)
        if response.status_code not in RETRYABLE_STATUS or attempt >= settings.llm_max_retries:
            return response
        fallback = _retry_fallback_seconds(attempt, settings.llm_retry_backoff_seconds)
        wait_seconds = _retry_after_seconds(response, fallback)
        LOGGER.warning(
            "LLM API HTTP %s; reintento %s/%s en %.1f s",
            response.status_code, attempt + 1, settings.llm_max_retries, wait_seconds,
        )
        await asyncio.sleep(wait_seconds)
    return response


def _response_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        return str(content)
    except Exception as exc:
        raise RuntimeError(f"Respuesta Vision inesperada: {str(data)[:1000]}") from exc


def _raise_api_error(response: httpx.Response, endpoint: str, profile: VisionProfile) -> None:
    if response.status_code < 400:
        return
    body = response.text[:1000]
    hint = ""
    if response.status_code == 404 and "generativelanguage.googleapis.com" in endpoint:
        hint = " Verificá el modelo configurado y que la clave pertenezca a Gemini API/Google AI Studio."
    raise RuntimeError(f"{profile.name} ({profile.model}) devolvió HTTP {response.status_code}: {body}{hint}")


async def _call_profile(profile: VisionProfile, payload: dict[str, Any], settings: Settings, timeout: float) -> str:
    if not profile.enabled:
        raise RuntimeError(f"Perfil {profile.name} desactivado.")
    if not profile.api_base or not profile.api_key or not profile.model:
        raise RuntimeError(f"Perfil {profile.name} incompleto: falta URL, API key o modelo.")
    endpoint = _endpoint_from_base(profile.api_base)
    request_payload = dict(payload)
    request_payload["model"] = profile.model
    LOGGER.info("Vision %s -> %s | model=%s", profile.name, endpoint, profile.model)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await _post_with_retries(client, endpoint, _headers(profile), request_payload, settings)
        _raise_api_error(response, endpoint, profile)
        data = response.json()
    return _response_content(data)


async def _call_with_failover(payload: dict[str, Any], settings: Settings, timeout: float,
                              count_metrics: bool = True) -> tuple[str, VisionProfile]:
    primary, backup = _primary_profile(settings), _backup_profile(settings)
    try:
        content = await _call_profile(primary, payload, settings, timeout)
        if count_metrics:
            _record_provider_result("primary", True)
        return content, primary
    except Exception as primary_exc:
        primary_error = str(primary_exc)
        if count_metrics:
            _record_provider_result("primary", False, primary_error)
        LOGGER.warning("LLM principal falló; evaluando backup: %s", primary_error)
        if not backup.configured:
            raise RuntimeError(f"LLM principal falló y no hay backup configurado: {primary_error}") from primary_exc
        if count_metrics:
            _record_failover()
        try:
            content = await _call_profile(backup, payload, settings, timeout)
            if count_metrics:
                _record_provider_result("backup", True)
            LOGGER.info("Failover LLM exitoso -> backup model=%s", backup.model)
            return content, backup
        except Exception as backup_exc:
            backup_error = str(backup_exc)
            if count_metrics:
                _record_provider_result("backup", False, backup_error)
            raise RuntimeError(
                f"Fallaron ambos perfiles LLM. Principal: {primary_error} | Backup: {backup_error}"
            ) from backup_exc


def _test_payload() -> dict[str, Any]:
    return {
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Prueba de conectividad Vision. Respondé sólo JSON: {\"ok\": true}"},
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_DATA_URI}},
        ]}],
    }


async def _test_profile(profile: VisionProfile, settings: Settings) -> dict[str, Any]:
    if not profile.enabled:
        return {"enabled": False, "configured": False, "ok": None, "name": profile.name}
    if not profile.configured:
        return {"enabled": True, "configured": False, "ok": False, "name": profile.name,
                "model": profile.model or None, "error": "Perfil incompleto: falta URL, API key o modelo."}
    try:
        content = await _call_profile(profile, _test_payload(), settings, timeout=60)
        parsed = _extract_json(content)
        return {"enabled": True, "configured": True, "ok": True, "name": profile.name,
                "model": profile.model, "endpoint": _endpoint_from_base(profile.api_base), "response": parsed}
    except Exception as exc:
        return {"enabled": True, "configured": True, "ok": False, "name": profile.name,
                "model": profile.model, "error": str(exc)}


async def test_vision_api(settings: Settings) -> dict[str, Any]:
    primary = await _test_profile(_primary_profile(settings), settings)
    backup = await _test_profile(_backup_profile(settings), settings)
    return {"ok": bool(primary.get("ok") or backup.get("ok")), "primary": primary, "backup": backup}


def _analysis_payload(path: Path, page: int, tile: str) -> dict[str, Any]:
    user_text = (
        f"Página {page}, recorte {tile}. Extraé todos los productos y ofertas visibles. "
        f"Año actual de referencia: {datetime.now().year}. Si la vigencia muestra sólo día/mes y es "
        "claramente el catálogo actual, usá ese año; si hay duda dejá la fecha en null."
    )
    return {
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": _data_uri(path), "detail": "high"}},
            ]},
        ],
    }


async def analyze_image(path: Path, page: int, tile: str, settings: Settings) -> dict[str, Any]:
    if not settings.vision_enabled:
        return {"catalog_valid_from": None, "catalog_valid_until": None, "products": []}
    content, profile = await _call_with_failover(_analysis_payload(path, page, tile), settings, timeout=120)
    parsed = _extract_json(content)
    if not isinstance(parsed.get("products", []), list):
        raise RuntimeError(f"Perfil {profile.name}: JSON válido pero products no es una lista.")
    parsed["provider_used"] = profile.name
    parsed["provider_model"] = profile.model
    for item in parsed.get("products") or []:
        item["page"] = page
        item["tile"] = tile
        item["llm_provider"] = profile.name
        item["llm_model"] = profile.model
        item["sin_tacc"] = None
    return parsed


def _sin_tacc_payload(path: Path, offers: list[dict[str, Any]]) -> dict[str, Any]:
    product_list = [
        {
            "id": int(item["id"]),
            "product": " ".join(str(item.get(k) or "").strip() for k in ("brand", "name", "variant", "presentation") if str(item.get(k) or "").strip()),
        }
        for item in offers
    ]
    return {
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SIN_TACC_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Productos de esta imagen:\n" + json.dumps(product_list, ensure_ascii=False)},
                {"type": "image_url", "image_url": {"url": _data_uri(path), "detail": "high"}},
            ]},
        ],
    }


async def verify_sin_tacc_image(path: Path, offers: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """Second pass, only after offers already exist in SQLite. Returns results keyed by DB offer ID."""
    food = [x for x in offers if x.get("is_food") in (1, True)]
    if not food:
        return {"results": [], "provider_used": None, "provider_model": None}
    content, profile = await _call_with_failover(_sin_tacc_payload(path, food), settings, timeout=120)
    parsed = _extract_json(content)
    results = parsed.get("results")
    if not isinstance(results, list):
        raise RuntimeError(f"Verificación SIN TACC ({profile.name}): results no es una lista.")
    allowed_ids = {int(x["id"]) for x in food}
    normalized = []
    seen: set[int] = set()
    for row in results:
        try:
            oid = int(row.get("id"))
        except Exception:
            continue
        if oid not in allowed_ids or oid in seen:
            continue
        value = row.get("sin_tacc")
        if value not in (True, False, None):
            value = None
        normalized.append({"id": oid, "sin_tacc": value})
        seen.add(oid)
    # IDs omitted by the model are explicitly left unverified.
    for oid in allowed_ids - seen:
        normalized.append({"id": oid, "sin_tacc": None})
    return {"results": normalized, "provider_used": profile.name, "provider_model": profile.model}


def deduplicate_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
