import json
import sqlite3
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper.db")


def _get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT,
            start_url TEXT,
            total_count INTEGER,
            created_at TEXT,
            data_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE,
            enabled INTEGER DEFAULT 1,
            fail_count INTEGER DEFAULT 0,
            added_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_record(task_name: str, start_url: str, data: List[Dict[str, str]]) -> int:
    init_db()
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO scrape_records (task_name, start_url, total_count, created_at, data_json) VALUES (?, ?, ?, ?, ?)",
        (task_name or "未命名", start_url, len(data), datetime.now().isoformat(), json.dumps(data, ensure_ascii=False)),
    )
    record_id = cur.lastrowid
    conn.commit()
    conn.close()
    return record_id




def list_records(limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, task_name, start_url, total_count, created_at FROM scrape_records ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = [
        {
            "id": r[0],
            "task_name": r[1],
            "start_url": r[2],
            "total_count": r[3],
            "created_at": r[4],
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return rows


def get_record(record_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM scrape_records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "task_name": row[1],
        "start_url": row[2],
        "total_count": row[3],
        "created_at": row[4],
        "data": json.loads(row[5]),
    }


def delete_record(record_id: int):
    init_db()
    conn = _get_conn()
    conn.execute("DELETE FROM scrape_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


def add_proxy(address: str):
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO proxies (address, added_at) VALUES (?, ?)",
            (address, datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def list_proxies() -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    cur = conn.execute("SELECT address, enabled, fail_count FROM proxies ORDER BY id DESC")
    rows = [{"address": r[0], "enabled": bool(r[1]), "fail_count": r[2]} for r in cur.fetchall()]
    conn.close()
    return rows


def delete_proxy(address: str):
    init_db()
    conn = _get_conn()
    conn.execute("DELETE FROM proxies WHERE address = ?", (address,))
    conn.commit()
    conn.close()


def mark_proxy_fail(address: str):
    init_db()
    conn = _get_conn()
    conn.execute("UPDATE proxies SET fail_count = fail_count + 1 WHERE address = ?", (address,))
    conn.commit()
    conn.close()
