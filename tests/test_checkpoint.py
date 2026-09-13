import json

import checkpoint


def test_checkpoint_roundtrip(tmp_path):
    path = str(tmp_path / "job.json")
    checkpoint.save(path, {"page": 3, "url": "https://example.com?p=3", "cursor": "abc"})
    assert checkpoint.load(path)["page"] == 3
    assert checkpoint.load(path)["cursor"] == "abc"


def test_checkpoint_invalid_file_returns_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    assert checkpoint.load(str(path)) == {}
