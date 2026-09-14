"""Migrate legacy scrape_records.data_json rows into scrape_rows."""

import json
import sqlite3
import sys


def migrate(path: str, drop_legacy: bool = False) -> int:
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
    if drop_legacy:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(scrape_records)")]
        if "data_json" in cols:
            conn.execute("ALTER TABLE scrape_records RENAME TO scrape_records_legacy")
            conn.execute("CREATE TABLE scrape_records (id INTEGER PRIMARY KEY, task_name TEXT, start_url TEXT, total_count INTEGER, created_at TEXT)")
            conn.execute("INSERT INTO scrape_records SELECT id,task_name,start_url,total_count,created_at FROM scrape_records_legacy")
            conn.execute("DROP TABLE scrape_records_legacy")
    conn.commit(); conn.close()
    return moved


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法: python migrate_db.py scraper.db")
    print(f"已迁移 {migrate(sys.argv[1])} 条记录")
