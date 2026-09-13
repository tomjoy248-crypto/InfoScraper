import json
import os
from typing import List, Dict

import pandas as pd
from redact import redact


def export_csv(data: List[Dict[str, str]], path: str):
    df = pd.DataFrame(redact(data))
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_excel(data: List[Dict[str, str]], path: str):
    df = pd.DataFrame(redact(data))
    df.to_excel(path, index=False, engine="openpyxl")


def export_json(data: List[Dict[str, str]], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(redact(data), f, ensure_ascii=False, indent=2)


def export(data: List[Dict[str, str]], path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        export_csv(data, path)
    elif ext in (".xlsx", ".xls"):
        export_excel(data, path)
    elif ext == ".json":
        export_json(data, path)
    else:
        raise ValueError(f"不支持的导出格式: {ext}")
