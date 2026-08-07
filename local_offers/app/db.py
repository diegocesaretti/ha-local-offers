from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


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
    allowed = {"title", "valid_from", "valid_until", "page_count", "status", "error"}
    pairs = [(k, v) for k, v in fields.items() if k in allowed]
    if not pairs:
        return
    sql = ", ".join(f"{k} = ?" for k, _ in pairs)
    values = [v for _, v in pairs] + [catalog_id]
    with connect() as conn:
        conn.execute(f"UPDATE catalogs SET {sql} WHERE id = ?", values)


def replace_offers(catalog_id: int, source: str, offers: Iterable[dict[str, Any]]) -> int:
    rows = list(offers)
    with connect() as conn:
        conn.execute("DELETE FROM offers WHERE catalog_id = ?", (catalog_id,))
        for item in rows:
            conn.execute(
                """INSERT INTO offers
                   (catalog_id, source, page, brand, name, variant, presentation, price,
                    previous_price, promotion_text, confidence, raw_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
