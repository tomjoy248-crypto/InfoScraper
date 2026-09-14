import json
import sqlite3

from migrate_db import migrate
import database


def test_migrate_legacy_json(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE scrape_records (id INTEGER PRIMARY KEY, data_json TEXT)")
    conn.execute("INSERT INTO scrape_records VALUES (1, ?)", (json.dumps([{"id": "a"}]),))
    conn.commit(); conn.close()
    assert migrate(path) == 1
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT data_json FROM scrape_records").fetchone()[0] == ""
    assert conn.execute("SELECT row_json FROM scrape_rows").fetchone()[0] == '{"id": "a"}'
    conn.close()

def test_record_rows_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "rows.db"))
    database.init_db()
    rid = database.save_record_stream("t", "https://example.com", ({"n": i} for i in range(5)))
    assert database.get_record_rows(rid, limit=2, offset=2) == [{"n": 2}, {"n": 3}]
