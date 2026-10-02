import database


def test_existing_keys_supports_non_ascii_and_punctuation(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "keys.db"))
    record_id = database.save_record_stream("keys", "https://example.test", [{"中文名": "张三", "id-code": "A-1"}])
    assert record_id
    assert database.existing_keys("keys", ["中文名", "id-code"]) == {("张三", "A-1")}


def test_stream_write_large_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "stress.db"))
    record_id = database.save_record_stream(
        "stress", "https://example.com", ({"id": i, "value": str(i)} for i in range(10000)), batch_size=128
    )
    assert database.count_record_rows(record_id) == 10000
    assert database.get_record_rows(record_id, limit=2, offset=9998) == [
        {"id": 9998, "value": "9998"}, {"id": 9999, "value": "9999"}
    ]
