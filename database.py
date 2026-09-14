import json
import sqlite3
import os
import time
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
    conn.execute("CREATE TABLE IF NOT EXISTS scrape_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL, row_json TEXT NOT NULL)")
    conn.commit()
    # Automatically migrate legacy JSON payloads on startup.
    try:
        legacy = conn.execute("SELECT id, data_json FROM scrape_records WHERE data_json IS NOT NULL AND data_json != ''").fetchall()
        for record_id, payload in legacy:
            try:
                rows = json.loads(payload)
                if isinstance(rows, list):
                    conn.executemany("INSERT INTO scrape_rows (record_id,row_json) VALUES (?,?)", [(record_id, json.dumps(r, ensure_ascii=False)) for r in rows])
                conn.execute("UPDATE scrape_records SET data_json='' WHERE id=?", (record_id,))
            except (TypeError, ValueError):
                continue
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE proxies ADD COLUMN cooldown_until REAL DEFAULT 0")
        conn.execute("ALTER TABLE proxies ADD COLUMN latency REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.close()


def check_proxy(address: str, timeout: float = 5.0) -> bool:
    """Check proxy reachability with a lightweight HTTPS request."""
    try:
        import requests
        started = time.monotonic(); response = requests.get("https://www.google.com/generate_204", proxies={"http": address, "https": address}, timeout=timeout)
        conn = _get_conn(); conn.execute("UPDATE proxies SET latency=? WHERE address=?", (time.monotonic() - started, address)); conn.commit(); conn.close()
        return response.status_code < 500
    except Exception:
        return False


def set_proxy_enabled(address: str, enabled: bool) -> None:
    """Enable or disable a proxy after health evaluation."""
    init_db(); conn = _get_conn(); conn.execute("UPDATE proxies SET enabled=?, cooldown_until=? WHERE address=?", (1 if enabled else 0, 0 if enabled else time.time() + 300, address)); conn.commit(); conn.close()


def mark_proxy_success(address: str) -> None:
    """Reset failure count after a successful health check."""
    init_db(); conn = _get_conn(); conn.execute("UPDATE proxies SET fail_count=0, enabled=1 WHERE address=?", (address,)); conn.commit(); conn.close()


def save_record(task_name: str, start_url: str, data: List[Dict[str, str]]) -> int:
    return save_record_stream(task_name, start_url, data)


def save_record_stream(task_name: str, start_url: str, rows, batch_size: int = 500) -> int:
    """Persist rows incrementally in a normalized table."""
    init_db(); conn = _get_conn()
    # Rows are stored exclusively in scrape_rows; data_json is left NULL for
    # backwards-compatible schemas and is never read by the application.
    cur = conn.execute("INSERT INTO scrape_records (task_name,start_url,total_count,created_at,data_json) VALUES (?,?,?,?,NULL)",
                       (task_name or "未命名", start_url, 0, datetime.now().isoformat()))
    record_id = cur.lastrowid; count = 0; batch = []
    for row in rows:
        batch.append((record_id, json.dumps(row, ensure_ascii=False))); count += 1
        if len(batch) >= batch_size:
            conn.executemany("INSERT INTO scrape_rows (record_id,row_json) VALUES (?,?)", batch); conn.commit(); batch.clear()
    if batch: conn.executemany("INSERT INTO scrape_rows (record_id,row_json) VALUES (?,?)", batch)
    conn.execute("UPDATE scrape_records SET total_count=? WHERE id=?", (count, record_id)); conn.commit(); conn.close()
    return record_id


def existing_keys(task_name: str, keys: List[str]) -> set:
    """Return keys already stored for a task for cross-run incremental filtering."""
    if not keys:
        return set()
    init_db(); conn = _get_conn(); result = set()
    records = conn.execute("SELECT id FROM scrape_records WHERE task_name=?", (task_name,)).fetchall()
    for (record_id,) in records:
        rows = conn.execute("SELECT row_json FROM scrape_rows WHERE record_id=?", (record_id,)).fetchall()
        result.update(tuple(str(row.get(k, "")).strip() for k in keys) for row in (json.loads(x[0]) for x in rows))
    conn.close(); return result




def list_records(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, task_name, start_url, total_count, created_at FROM scrape_records ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
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
    if not row:
        conn.close()
        return None
    data = [json.loads(r[0]) for r in conn.execute("SELECT row_json FROM scrape_rows WHERE record_id=? ORDER BY id", (record_id,)).fetchall()]
    conn.close()
    return {
        "id": row[0],
        "task_name": row[1],
        "start_url": row[2],
        "total_count": row[3],
        "created_at": row[4],
        "data": data,
    }

def get_record_rows(record_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Read a bounded page of rows for large historical records."""
    init_db(); conn = _get_conn()
    rows = conn.execute("SELECT row_json FROM scrape_rows WHERE record_id=? ORDER BY id LIMIT ? OFFSET ?", (record_id, limit, offset)).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

def count_record_rows(record_id: int) -> int:
    """Return row count without loading historical payloads."""
    init_db(); conn = _get_conn()
    value = conn.execute("SELECT COUNT(*) FROM scrape_rows WHERE record_id=?", (record_id,)).fetchone()[0]
    conn.close(); return int(value)


def delete_record(record_id: int):
    init_db()
    conn = _get_conn()
    conn.execute("DELETE FROM scrape_rows WHERE record_id = ?", (record_id,))
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
    conn.execute("UPDATE proxies SET enabled=1, cooldown_until=0 WHERE enabled=0 AND cooldown_until > 0 AND cooldown_until <= ?", (time.time(),))
    conn.commit()
    cur = conn.execute("SELECT address, enabled, fail_count, latency, cooldown_until FROM proxies ORDER BY enabled DESC, CASE WHEN latency=0 THEN 999999 ELSE latency END ASC, id DESC")
    rows = [{"address": r[0], "enabled": bool(r[1]), "fail_count": r[2], "latency": r[3] or 0, "cooldown_until": r[4] or 0} for r in cur.fetchall()]
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
    conn.execute("UPDATE proxies SET fail_count = fail_count + 1, enabled = CASE WHEN fail_count + 1 >= 3 THEN 0 ELSE enabled END, cooldown_until = CASE WHEN fail_count + 1 >= 3 THEN ? ELSE cooldown_until END WHERE address = ?", (time.time() + 300, address))
    conn.commit()
    conn.close()
