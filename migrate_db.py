"""Migrate legacy scrape_records.data_json rows into scrape_rows."""

import json
import sqlite3
import sys


def migrate(path: str) -> int:
    """Move legacy JSON payloads into normalized rows and clear the payload."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS scrape_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL, row_json TEXT NOT NULL)")
    moved = 0
    for record_id, payload in conn.execute("SELECT id, data_json FROM scrape_records WHERE data_json IS NOT NULL AND data_json != ''"):
        try:
            rows = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        conn.executemany("INSERT INTO scrape_rows(record_id,row_json) VALUES (?,?)",
                         [(record_id, json.dumps(row, ensure_ascii=False)) for row in rows])
        conn.execute("UPDATE scrape_records SET data_json='' WHERE id=?", (record_id,))
        moved += len(rows)
    conn.commit(); conn.close()
    return moved


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法: python migrate_db.py scraper.db")
    print(f"已迁移 {migrate(sys.argv[1])} 条记录")
