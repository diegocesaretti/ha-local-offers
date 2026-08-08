from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from . import db
from .config import Settings

LOGGER = logging.getLogger(__name__)
CACHE_PREFIX = "anmat_brand_v1:"


def _norm(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _product_text(item: dict[str, Any]) -> str:
    # ANMAT's denomination does not necessarily include pack size/presentation.
    return _norm(" ".join(
        str(item.get(k) or "")
        for k in ("brand", "name", "variant")
    ))


def _cache_key(brand: str) -> str:
    digest = hashlib.sha1(_norm(brand).encode("utf-8")).hexdigest()[:20]
    return CACHE_PREFIX + digest


def _load_cache(brand: str, max_age_days: int) -> list[dict[str, str]] | None:
    raw = db.get_state(_cache_key(brand))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        checked = datetime.fromisoformat(str(data.get("checked_at")).replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds() / 86400
        rows = data.get("rows")
        if age_days <= max_age_days and isinstance(rows, list):
            return rows
    except Exception:
        return None
    return None


def _save_cache(brand: str, rows: list[dict[str, str]]) -> None:
    db.set_state(
        _cache_key(brand),
        json.dumps({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "rows": rows,
        }, ensure_ascii=False),
    )


def _field_map(form) -> tuple[dict[str, str], dict[str, str]]:
    labels: dict[str, str] = {}
    for label in form.find_all("label"):
        target = label.get("for")
        if target:
            labels[str(target)] = _norm(label.get_text(" ", strip=True))

    inputs: dict[str, str] = {}
    selects: dict[str, str] = {}
    for tag in form.find_all(["input", "select"]):
        name = tag.get("name")
        if not name:
            continue
        ident = str(tag.get("id") or "")
        descriptor = " ".join([
            _norm(name),
            _norm(ident),
            labels.get(ident, ""),
            _norm(tag.get("placeholder")),
        ])
        if tag.name == "select":
            selects[str(name)] = descriptor
        else:
            inputs[str(name)] = descriptor
    return inputs, selects


def _find_field(fields: dict[str, str], needle: str) -> str | None:
    for name, desc in fields.items():
        if needle in desc:
            return name
    return None


def _form_payload(form, brand: str) -> tuple[dict[str, str], str | None]:
    payload: dict[str, str] = {}
    for tag in form.find_all("input"):
        name = tag.get("name")
        if not name:
            continue
        typ = str(tag.get("type") or "text").lower()
        if typ == "hidden":
            payload[str(name)] = str(tag.get("value") or "")

    inputs, selects = _field_map(form)
    brand_field = _find_field(inputs, "marca") or _find_field(inputs, "fantasia")
    if not brand_field:
        return payload, None
    payload[brand_field] = brand

    state_field = _find_field(selects, "estado")
    if state_field:
        select = form.find("select", attrs={"name": state_field})
        if select:
            for option in select.find_all("option"):
                text = _norm(option.get_text(" ", strip=True))
                if text == "vigente" or "vigente" in text:
                    payload[state_field] = str(option.get("value") or option.get_text(strip=True))
                    break

    for tag in form.find_all(["button", "input"]):
        typ = str(tag.get("type") or "").lower()
        text = _norm(tag.get_text(" ", strip=True) if tag.name == "button" else tag.get("value"))
        if typ in {"submit", "button"} and "buscar" in text and tag.get("name"):
            payload[str(tag.get("name"))] = str(tag.get("value") or tag.get_text(strip=True) or "Buscar")
            break
    return payload, brand_field


def _choose_search_form(html: str):
    soup = BeautifulSoup(html, "html.parser")
    candidates = soup.find_all("form")
    for form in candidates:
        text = _norm(form.get_text(" ", strip=True))
        if "marca" in text and ("denominacion" in text or "rnpa" in text):
            return form
    return candidates[0] if candidates else None


def _parse_rows(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    best: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 2:
            continue
        headers = [_norm(x.get_text(" ", strip=True)) for x in trs[0].find_all(["th", "td"])]
        joined = " ".join(headers)
        if not any(word in joined for word in ("marca", "denominacion", "rnpa", "estado")):
            continue
        rows: list[dict[str, str]] = []
        for tr in trs[1:]:
            cells = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"])]
            if not cells:
                continue
            row = {headers[i] if i < len(headers) and headers[i] else f"c{i}": value for i, value in enumerate(cells)}
            row["_text"] = " | ".join(cells)
            state_text = " ".join(v for k, v in row.items() if "estado" in k)
            if state_text and "vigente" not in _norm(state_text):
                continue
            rows.append(row)
        if len(rows) > len(best):
            best = rows
    return best


def _row_match_text(row: dict[str, str]) -> str:
    selected = [
        value
        for key, value in row.items()
        if any(token in key for token in ("marca", "fantasia", "denominacion", "nombre"))
    ]
    return _norm(" ".join(selected) if selected else row.get("_text"))


def _score(product: dict[str, Any], row: dict[str, str]) -> float:
    ptext = _product_text(product)
    rtext = _row_match_text(row)
    if not ptext or not rtext:
        return 0.0
    brand = _norm(product.get("brand"))
    if brand:
        row_brand_parts = [v for k, v in row.items() if "marca" in k or "fantasia" in k]
        row_brand = _norm(" ".join(row_brand_parts))
        if row_brand:
            br = SequenceMatcher(None, brand, row_brand).ratio()
            if br < 0.72 and not (set(brand.split()) & set(row_brand.split())):
                return 0.0
    seq = SequenceMatcher(None, ptext, rtext).ratio()
    pt, rt = set(ptext.split()), set(rtext.split())
    jaccard = len(pt & rt) / max(1, len(pt | rt))
    containment = len(pt & rt) / max(1, len(pt))
    return min(1.0, seq * 0.35 + jaccard * 0.30 + containment * 0.35)


async def _fetch_brand_rows(brand: str, settings: Settings) -> tuple[list[dict[str, str]], str | None]:
    cached = _load_cache(brand, settings.anmat_cache_days)
    if cached is not None:
        return cached, None

    headers = {"User-Agent": "HA-Local-Offers/0.3.1 (+Home Assistant App)"}
    async with httpx.AsyncClient(timeout=settings.anmat_timeout_seconds, follow_redirects=True, headers=headers) as client:
        home = await client.get(settings.anmat_url)
        home.raise_for_status()
        form = _choose_search_form(home.text)
        if form is None:
            raise RuntimeError("ANMAT: no se encontró el formulario público de búsqueda.")
        payload, brand_field = _form_payload(form, brand)
        if not brand_field:
            raise RuntimeError("ANMAT: no se pudo identificar el campo Marca/Nombre de fantasía.")
        action = urljoin(str(home.url), str(form.get("action") or ""))
        method = str(form.get("method") or "get").lower()
        if method == "post":
            result = await client.post(action, data=payload)
        else:
            result = await client.get(action, params=payload)
        result.raise_for_status()
        rows = _parse_rows(result.text)
        _save_cache(brand, rows)
        return rows, str(result.url)


async def match_products_anmat(products: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """Best-effort LIALG matcher. Only strong, unambiguous Vigente matches are returned."""
    if not settings.anmat_enabled:
        return {"matches": {}, "queries": 0, "brands": 0, "errors": []}

    by_brand: dict[str, list[dict[str, Any]]] = {}
    for item in products:
        brand = str(item.get("brand") or "").strip()
        if not brand:
            continue
        by_brand.setdefault(brand, []).append(item)

    matches: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    queries = 0

    for brand, items in by_brand.items():
        try:
            rows, source_url = await _fetch_brand_rows(brand, settings)
            queries += 1
            for item in items:
                scored = sorted(
                    ((row, _score(item, row)) for row in rows),
                    key=lambda pair: pair[1],
                    reverse=True,
                )
                if not scored:
                    continue
                best_row, best_score = scored[0]
                second_score = scored[1][1] if len(scored) > 1 else 0.0
                if best_score < settings.anmat_match_threshold:
                    continue
                if second_score >= best_score - 0.035:
                    continue
                oid = int(item["id"])
                matches[oid] = {
                    "score": round(best_score, 3),
                    "state": "Vigente",
                    "record": best_row.get("_text"),
                    "url": source_url or settings.anmat_url,
                }
        except Exception as exc:
            errors.append(f"{brand}: {exc}")
            LOGGER.warning("ANMAT no disponible para marca %s: %s", brand, exc)
        if settings.anmat_delay_seconds > 0:
            await asyncio.sleep(settings.anmat_delay_seconds)

    return {
        "matches": matches,
        "queries": queries,
        "brands": len(by_brand),
        "errors": errors[:10],
    }
