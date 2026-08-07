from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

CHECKPOINT_ROOT = Path("/data/checkpoints")
CHECKPOINT_VERSION = 1


def _folder(catalog_sha256: str) -> Path:
    return CHECKPOINT_ROOT / catalog_sha256[:24]


def _path(catalog_sha256: str, page: int, tile: str) -> Path:
    safe_tile = "".join(ch for ch in str(tile) if ch.isalnum() or ch in "-_") or "full"
    return _folder(catalog_sha256) / f"p{int(page):04d}-{safe_tile}.json"


def clear_catalog(catalog_sha256: str) -> None:
    folder = _folder(catalog_sha256)
    if folder.exists():
        shutil.rmtree(folder)


def load_chunk(catalog_sha256: str, page: int, tile: str) -> dict[str, Any] | None:
    path = _path(catalog_sha256, page, tile)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("checkpoint_version") != CHECKPOINT_VERSION:
            return None
        result = data.get("result")
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def save_chunk(catalog_sha256: str, page: int, tile: str, result: dict[str, Any]) -> None:
    folder = _folder(catalog_sha256)
    folder.mkdir(parents=True, exist_ok=True)
    path = _path(catalog_sha256, page, tile)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "page": int(page),
        "tile": str(tile),
        "result": result,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def count_chunks(catalog_sha256: str) -> int:
    folder = _folder(catalog_sha256)
    if not folder.exists():
        return 0
    return sum(1 for p in folder.glob("*.json") if p.is_file())
