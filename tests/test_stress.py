import database


def test_stream_write_large_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "stress.db"))
    record_id = database.save_record_stream(
        "stress", "https://example.com", ({"id": i, "value": str(i)} for i in range(10000)), batch_size=128
    )
    assert database.count_record_rows(record_id) == 10000
    assert database.get_record_rows(record_id, limit=2, offset=9998) == [
        {"id": 9998, "value": "9998"}, {"id": 9999, "value": "9999"}
    ]
