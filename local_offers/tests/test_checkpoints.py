from app import checkpoints


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoints, "CHECKPOINT_ROOT", tmp_path)
    result = {
        "catalog_valid_from": "2026-08-01",
        "products": [{"name": "Yerba", "price": 1234, "page": 3, "tile": "q2"}],
        "provider_used": "primary",
    }
    checkpoints.save_chunk("abcdef1234567890", 3, "q2", result)
    assert checkpoints.count_chunks("abcdef1234567890") == 1
    assert checkpoints.load_chunk("abcdef1234567890", 3, "q2") == result


def test_force_clear_checkpoint_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoints, "CHECKPOINT_ROOT", tmp_path)
    checkpoints.save_chunk("abcdef1234567890", 1, "full", {"products": []})
    checkpoints.save_chunk("abcdef1234567890", 2, "full", {"products": []})
    assert checkpoints.count_chunks("abcdef1234567890") == 2
    checkpoints.clear_catalog("abcdef1234567890")
    assert checkpoints.count_chunks("abcdef1234567890") == 0
