import json
import sqlite3

from migrate_db import migrate


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
