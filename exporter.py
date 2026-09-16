import json
import os
import csv
from typing import List, Dict

from redact import redact

def _safe_cell(value):
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

def _fields(rows):
    fields = []
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    return fields


def export_csv(data: List[Dict[str, str]], path: str):
    rows = redact(data); fields = _fields(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
        writer.writerows([{k: _safe_cell(v) for k, v in row.items()} for row in rows])


def export_excel(data: List[Dict[str, str]], path: str):
    from openpyxl import Workbook
    rows = redact(data); fields = _fields(rows)
    wb = Workbook(); ws = wb.active; ws.append(fields)
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    for row in rows: ws.append([_safe_cell(ILLEGAL_CHARACTERS_RE.sub("", str(row.get(k, "")))) for k in fields])
    wb.save(path)


def export_json(data: List[Dict[str, str]], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(redact(data), f, ensure_ascii=False, indent=2)


def export(data: List[Dict[str, str]], path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        export_csv(data, path)
    elif ext == ".xlsx":
        export_excel(data, path)
    elif ext == ".xls":
        raise ValueError("不支持旧式 .xls，请改用 .xlsx 或 .csv")
    elif ext == ".json":
        export_json(data, path)
    else:
        raise ValueError(f"不支持的导出格式: {ext}")
