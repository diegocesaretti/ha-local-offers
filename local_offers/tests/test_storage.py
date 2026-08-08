from pathlib import Path

from app import db, storage
from app.config import Settings


def _write(path: Path, data: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_cleanup_keeps_current_and_incomplete(monkeypatch, tmp_path):
    db_path = tmp_path / "offers.db"
    catalogs = tmp_path / "catalogs"
    rendered = tmp_path / "rendered"
    checkpoints = tmp_path / "checkpoints"
    anmat = tmp_path / "anmat"

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    monkeypatch.setattr(storage, "CATALOG_ROOT", catalogs)
    monkeypatch.setattr(storage, "RENDER_ROOT", rendered)
    monkeypatch.setattr(storage, "CHECKPOINT_ROOT", checkpoints)
    monkeypatch.setattr(storage, "ANMAT_ROOT", anmat)
    db.init_db()

    old_pdf = catalogs / "almacor" / "old" / "catalog.pdf"
    new_pdf = catalogs / "almacor" / "new" / "catalog.pdf"
    err_pdf = catalogs / "caracol" / "err" / "catalog.pdf"
    for p in (old_pdf, new_pdf, err_pdf):
        _write(p, b"pdf")

    old_id = db.insert_catalog(source="Almacor", source_url="x", external_id=None, title="old", sha256="a" * 64, pdf_path=str(old_pdf), page_count=1)
    new_id = db.insert_catalog(source="Almacor", source_url="x", external_id=None, title="new", sha256="b" * 64, pdf_path=str(new_pdf), page_count=1)
    err_id = db.insert_catalog(source="Caracol", source_url="x", external_id=None, title="err", sha256="c" * 64, pdf_path=str(err_pdf), page_count=1)
    db.update_catalog(old_id, status="ready")
    db.update_catalog(new_id, status="ready")
    db.update_catalog(err_id, status="error")
    with db.connect() as conn:
        conn.execute("UPDATE catalogs SET created_at='2026-01-01T00:00:00+00:00' WHERE id=?", (old_id,))
        conn.execute("UPDATE catalogs SET created_at='2026-02-01T00:00:00+00:00' WHERE id=?", (new_id,))

    _write(rendered / "page.jpg", b"jpeg")
    _write(checkpoints / ("a" * 24) / "p0001-full.json", b"{}")
    _write(checkpoints / ("c" * 24) / "p0001-full.json", b"{}")

    result = storage.cleanup_storage(Settings(cleanup_enabled=True, keep_pdfs_per_source=1))

    assert not old_pdf.exists()
    assert new_pdf.exists()
    assert err_pdf.exists()  # incomplete/error PDF must survive for resume/reanalysis
    assert not rendered.exists()
    assert not (checkpoints / ("a" * 24)).exists()
    assert (checkpoints / ("c" * 24)).exists()
    assert result["deleted_pdfs"] == 1
