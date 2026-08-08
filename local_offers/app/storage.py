from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from . import db
from .config import Settings

LOGGER = logging.getLogger(__name__)
DATA_ROOT = Path('/data')
CATALOG_ROOT = DATA_ROOT / 'catalogs'
RENDER_ROOT = DATA_ROOT / 'rendered'
CHECKPOINT_ROOT = DATA_ROOT / 'checkpoints'
ANMAT_ROOT = DATA_ROOT / 'anmat'
DB_PATH = DATA_ROOT / 'offers.db'


def _size(path: Path) -> int:
    if not path.exists(): return 0
    if path.is_file():
        try: return path.stat().st_size
        except OSError: return 0
    total = 0
    for p in path.rglob('*'):
        if p.is_file():
            try: total += p.stat().st_size
            except OSError: pass
    return total


def storage_stats() -> dict[str, Any]:
    parts = {
        'database_bytes': _size(DB_PATH) + _size(DB_PATH.with_name('offers.db-wal')) + _size(DB_PATH.with_name('offers.db-shm')),
        'pdf_bytes': _size(CATALOG_ROOT),
        'render_bytes': _size(RENDER_ROOT),
        'checkpoint_bytes': _size(CHECKPOINT_ROOT),
        'anmat_bytes': _size(ANMAT_ROOT),
    }
    parts['total_bytes'] = sum(parts.values())
    return parts


def _catalog_rows() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            'SELECT id, source, sha256, pdf_path, status, created_at FROM catalogs ORDER BY created_at DESC'
        ).fetchall()]


def _retention(rows: list[dict[str, Any]], keep_per_source: int) -> tuple[set[Path], set[str]]:
    keep_paths: set[Path] = set()
    resume_hashes: set[str] = set()
    ready_count: dict[str, int] = {}
    seen_source: set[str] = set()

    # Rows arrive newest first. Only the newest non-ready catalog for a source deserves
    # resume protection; stale errors/downloads from older weeks are garbage.
    for row in rows:
        source = str(row.get('source') or '')
        status = str(row.get('status') or '')
        path_text = str(row.get('pdf_path') or '')
        is_latest_for_source = source not in seen_source
        if is_latest_for_source:
            seen_source.add(source)

        if status != 'ready':
            if is_latest_for_source and path_text:
                keep_paths.add(Path(path_text))
                resume_hashes.add(str(row.get('sha256') or '')[:24])
            continue

        count = ready_count.get(source, 0)
        if count < keep_per_source and path_text:
            keep_paths.add(Path(path_text))
            ready_count[source] = count + 1

    return keep_paths, resume_hashes


def _remove_empty_dirs(root: Path) -> None:
    if not root.exists(): return
    for p in sorted((x for x in root.rglob('*') if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
        try: p.rmdir()
        except OSError: pass


def _cleanup_app_state() -> int:
    removed = 0
    with db.connect() as conn:
        completed = [r[0] for r in conn.execute("SELECT key FROM app_state WHERE key LIKE 'gluten_text_complete:%' AND value='1'").fetchall()]
        for key in completed:
            catalog_id = key.rsplit(':', 1)[-1]
            cur = conn.execute("DELETE FROM app_state WHERE key LIKE ?", (f'gluten_text_offer:{catalog_id}:%',))
            removed += max(0, cur.rowcount)
        # v0.2/v0.3.1 leftovers no longer used by current code.
        for pattern in ('sin_tacc_chunk:%', 'sin_tacc_complete:%', 'anmat_brand_v1:%'):
            cur = conn.execute('DELETE FROM app_state WHERE key LIKE ?', (pattern,))
            removed += max(0, cur.rowcount)
    return removed


def cleanup_storage(settings: Settings) -> dict[str, Any]:
    before = storage_stats()
    if not settings.cleanup_enabled:
        return {'enabled': False, 'before': before, 'after': before}

    rows = _catalog_rows()
    keep_pdfs, resume_hashes = _retention(rows, settings.keep_pdfs_per_source)
    deleted_pdfs = 0
    deleted_checkpoint_dirs = 0

    # JPEG renders are fully reproducible working files.
    if RENDER_ROOT.exists():
        shutil.rmtree(RENDER_ROOT, ignore_errors=True)

    # Checkpoints survive only for the newest unfinished catalog of each source.
    if CHECKPOINT_ROOT.exists():
        for item in CHECKPOINT_ROOT.iterdir():
            if item.is_dir() and item.name not in resume_hashes:
                shutil.rmtree(item, ignore_errors=True)
                deleted_checkpoint_dirs += 1
            elif item.is_file() and item.suffix == '.tmp':
                item.unlink(missing_ok=True)

    # Keep current ready PDFs according to retention plus a current unfinished PDF for resume.
    if CATALOG_ROOT.exists():
        keep_resolved = {p.resolve() for p in keep_pdfs}
        for pdf in CATALOG_ROOT.rglob('catalog.pdf'):
            try: resolved = pdf.resolve()
            except OSError: resolved = pdf
            if resolved not in keep_resolved:
                try:
                    pdf.unlink()
                    deleted_pdfs += 1
                except OSError:
                    LOGGER.warning('No se pudo borrar PDF viejo %s', pdf)
        _remove_empty_dirs(CATALOG_ROOT)

    for root in (CATALOG_ROOT, CHECKPOINT_ROOT, ANMAT_ROOT):
        if root.exists():
            for tmp in root.rglob('*.tmp'):
                try: tmp.unlink()
                except OSError: pass

    state_rows_removed = _cleanup_app_state()
    after = storage_stats()
    freed = max(0, before['total_bytes'] - after['total_bytes'])
    result = {
        'enabled': True,
        'deleted_pdfs': deleted_pdfs,
        'deleted_checkpoint_dirs': deleted_checkpoint_dirs,
        'state_rows_removed': state_rows_removed,
        'freed_bytes': freed,
        'before': before,
        'after': after,
    }
    LOGGER.info('Limpieza almacenamiento: liberados %.1f MB, PDFs viejos=%s, checkpoints=%s', freed / 1048576, deleted_pdfs, deleted_checkpoint_dirs)
    return result
