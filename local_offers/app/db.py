from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


DB_PATH = Path("/data/offers.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS catalogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    external_id TEXT,
    title TEXT,
    sha256 TEXT NOT NULL UNIQUE,
    pdf_path TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    page_count INTEGER,
    status TEXT NOT NULL DEFAULT 'downloaded',
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalogs_source_created ON catalogs(source, created_at DESC);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    page INTEGER NOT NULL,
    brand TEXT,
    name TEXT NOT NULL,
    variant TEXT,
    presentation TEXT,
    price REAL,
    previous_price REAL,
    promotion_text TEXT,
    is_food INTEGER,
    sin_tacc INTEGER,
    confidence REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(catalog_id) REFERENCES catalogs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_offers_catalog ON offers(catalog_id);
CREATE INDEX IF NOT EXISTS idx_offers_name ON offers(name);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "offers", "is_food", "INTEGER")
        _ensure_column(conn, "offers", "sin_tacc", "INTEGER")
        # v0.2 migration: Heyzine is only the publishing platform; the store is Caracol.
        conn.execute("UPDATE catalogs SET source='Caracol' WHERE source='Heyzine'")
        conn.execute("UPDATE offers SET source='Caracol' WHERE source='Heyzine'")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog_by_hash(sha256: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM catalogs WHERE sha256 = ?", (sha256,)).fetchone()
        return dict(row) if row else None


def insert_catalog(*, source: str, source_url: str, external_id: str | None, title: str | None,
                   sha256: str, pdf_path: str, page_count: int | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO catalogs
               (source, source_url, external_id, title, sha256, pdf_path, page_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, source_url, external_id, title, sha256, pdf_path, page_count, utcnow()),
        )
        return int(cur.lastrowid)


def update_catalog(catalog_id: int, **fields: Any) -> None:
    allowed = {
        "source", "source_url", "title", "valid_from", "valid_until",
        "page_count", "status", "error"
    }
    pairs = [(k, v) for k, v in fields.items() if k in allowed]
    if not pairs:
        return
    sql = ", ".join(f"{k} = ?" for k, _ in pairs)
    values = [v for _, v in pairs] + [catalog_id]
    with connect() as conn:
        conn.execute(f"UPDATE catalogs SET {sql} WHERE id = ?", values)
        if "source" in fields:
            conn.execute("UPDATE offers SET source=? WHERE catalog_id=?", (fields["source"], catalog_id))


def _bool_db(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def replace_offers(catalog_id: int, source: str, offers: Iterable[dict[str, Any]]) -> int:
    rows = list(offers)
    with connect() as conn:
        conn.execute("DELETE FROM offers WHERE catalog_id = ?", (catalog_id,))
        for item in rows:
            conn.execute(
                """INSERT INTO offers
                   (catalog_id, source, page, brand, name, variant, presentation, price,
                    previous_price, promotion_text, is_food, sin_tacc, confidence, raw_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    catalog_id,
                    source,
                    int(item.get("page") or 0),
                    item.get("brand"),
                    item.get("name") or "Producto sin nombre",
                    item.get("variant"),
                    item.get("presentation"),
                    item.get("price"),
                    item.get("previous_price"),
                    item.get("promotion_text"),
                    _bool_db(item.get("is_food")),
                    _bool_db(item.get("sin_tacc")),
                    item.get("confidence"),
                    json.dumps(item, ensure_ascii=False),
                    utcnow(),
                ),
            )
    return len(rows)


def latest_catalogs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM catalogs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def list_offers(*, source: str | None = None, query: str | None = None, limit: int = 300,
                current_only: bool = True) -> list[dict[str, Any]]:
    where = []
    args: list[Any] = []
    if current_only:
        where.append("c.id = (SELECT c2.id FROM catalogs c2 WHERE c2.source=c.source AND c2.status='ready' ORDER BY c2.created_at DESC LIMIT 1)")
    if source:
        where.append("o.source = ?")
        args.append(source)
    if query:
        where.append("LOWER(COALESCE(o.brand,'') || ' ' || o.name || ' ' || COALESCE(o.variant,'')) LIKE ?")
        args.append(f"%{query.lower()}%")
    clause = " WHERE " + " AND ".join(where) if where else ""
    args.append(limit)
    sql = f"""
        SELECT o.*, c.valid_from, c.valid_until, c.source_url, c.title AS catalog_title
        FROM offers o
        JOIN catalogs c ON c.id=o.catalog_id
        {clause}
        ORDER BY o.source ASC, o.page ASC, o.id ASC
        LIMIT ?
    """
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("coca-cola", "coca cola")
    text = re.sub(r"\b(lts?|litros?)\b", " l ", text)
    text = re.sub(r"\b(grs?|gramos?)\b", " g ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _product_text(item: dict[str, Any]) -> str:
    return _normalize_text(" ".join(
        str(item.get(k) or "") for k in ("brand", "name", "variant")
    ))


def _amount_signature(item: dict[str, Any]) -> tuple[str, float] | None:
    text = _normalize_text(" ".join(
        str(item.get(k) or "") for k in ("presentation", "variant", "name")
    ))
    # Normalization removes comma/dot punctuation, so inspect the original text for decimals.
    original = " ".join(str(item.get(k) or "") for k in ("presentation", "variant", "name")).lower()
    original = original.replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilos?|g|gr|gramos?|l|lt|lts|litros?|ml|cc|u|un|unidad(?:es)?)\b", original)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        if unit.startswith("kg") or unit.startswith("kilo"):
            return ("weight", value * 1000)
        if unit in {"g", "gr"} or unit.startswith("gram"):
            return ("weight", value)
        if unit in {"l", "lt", "lts"} or unit.startswith("litro"):
            return ("volume", value * 1000)
        if unit in {"ml", "cc"}:
            return ("volume", value)
        return ("count", value)
    if re.search(r"\bkg\b", text):
        return ("weight", 1000.0)
    return None


def _compatible_amount(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, bool]:
    aa = _amount_signature(a)
    bb = _amount_signature(b)
    if not aa or not bb:
        return True, False
    if aa[0] != bb[0]:
        return False, False
    max_value = max(aa[1], bb[1], 1.0)
    close = abs(aa[1] - bb[1]) / max_value <= 0.04
    return close, close


def _match_score(a: dict[str, Any], b: dict[str, Any]) -> float:
    compatible, amount_match = _compatible_amount(a, b)
    if not compatible:
        return 0.0

    brand_a = _normalize_text(a.get("brand"))
    brand_b = _normalize_text(b.get("brand"))
    if brand_a and brand_b:
        brand_ratio = SequenceMatcher(None, brand_a, brand_b).ratio()
        if brand_ratio < 0.58 and not (set(brand_a.split()) & set(brand_b.split())):
            return 0.0
    else:
        brand_ratio = 0.0

    text_a = _product_text(a)
    text_b = _product_text(b)
    if not text_a or not text_b:
        return 0.0
    seq = SequenceMatcher(None, text_a, text_b).ratio()
    ta, tb = set(text_a.split()), set(text_b.split())
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    score = (seq * 0.58) + (jaccard * 0.42)
    if amount_match:
        score += 0.10
    if brand_a and brand_b and brand_ratio >= 0.78:
        score += 0.07
    return min(score, 1.0)


def _display_name(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(k) or "").strip()
        for k in ("brand", "name", "variant", "presentation")
        if str(item.get(k) or "").strip()
    )


def compare_current_offers(query: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    almacor = [x for x in list_offers(source="Almacor", limit=1000) if x.get("price") is not None]
    caracol = [x for x in list_offers(source="Caracol", limit=1000) if x.get("price") is not None]
    used_caracol: set[int] = set()
    matches: list[dict[str, Any]] = []
    qnorm = _normalize_text(query) if query else ""

    for a in almacor:
        best: dict[str, Any] | None = None
        best_score = 0.0
        for c in caracol:
            cid = int(c["id"])
            if cid in used_caracol:
                continue
            score = _match_score(a, c)
            if score > best_score:
                best, best_score = c, score
        if best is None or best_score < 0.64:
            continue

        display_name = _display_name(a) or _display_name(best)
        searchable = _normalize_text(display_name + " " + _display_name(best))
        if qnorm and qnorm not in searchable:
            continue

        used_caracol.add(int(best["id"]))
        pa = float(a["price"])
        pc = float(best["price"])
        difference = abs(pa - pc)
        if pa < pc:
            cheaper = "Almacor"
            cheaper_price = pa
        elif pc < pa:
            cheaper = "Caracol"
            cheaper_price = pc
        else:
            cheaper = "Igual"
            cheaper_price = pa
        difference_percent = (difference / cheaper_price * 100.0) if cheaper_price else 0.0
        verified_sources = [
            item["source"] for item in (a, best) if item.get("sin_tacc") == 1
        ]
        matches.append({
            "name": display_name,
            "match_score": round(best_score, 3),
            "almacor": a,
            "caracol": best,
            "difference": round(difference, 2),
            "difference_percent": round(difference_percent, 1),
            "cheaper_source": cheaper,
            "sin_tacc_verified": bool(verified_sources),
            "sin_tacc_verified_by": verified_sources,
        })

    matches.sort(key=lambda x: (x["difference_percent"], x["difference"]), reverse=True)
    return matches[:limit]


def get_catalog(catalog_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM catalogs WHERE id=?", (catalog_id,)).fetchone()
        return dict(row) if row else None


def stats() -> dict[str, Any]:
    current_filter = "c.id = (SELECT c2.id FROM catalogs c2 WHERE c2.source=c.source AND c2.status='ready' ORDER BY c2.created_at DESC LIMIT 1)"
    with connect() as conn:
        total_offers = conn.execute(
            f"SELECT COUNT(*) FROM offers o JOIN catalogs c ON c.id=o.catalog_id WHERE {current_filter}"
        ).fetchone()[0]
        historical_offers = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        total_catalogs = conn.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0]
        latest = conn.execute("SELECT created_at FROM catalogs ORDER BY created_at DESC LIMIT 1").fetchone()
        by_source = {
            row[0]: row[1]
            for row in conn.execute(
                f"SELECT o.source, COUNT(*) FROM offers o JOIN catalogs c ON c.id=o.catalog_id WHERE {current_filter} GROUP BY o.source"
            ).fetchall()
        }
        return {
            "offers": total_offers,
            "historical_offers": historical_offers,
            "catalogs": total_catalogs,
            "last_update": latest[0] if latest else None,
            "by_source": by_source,
        }


def set_state(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_state(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
