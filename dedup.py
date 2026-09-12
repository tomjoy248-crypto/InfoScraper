from typing import Dict, List, Optional


def deduplicate(data: List[Dict[str, str]], keys: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """根据指定字段去重，未指定则按整行去重。保留第一次出现的记录。"""
    seen = set()
    result = []
    for row in data:
        if keys:
            key = tuple(row.get(k, "").strip() for k in keys if k in row)
        else:
            key = tuple(sorted(row.items()))
        if not key or key not in seen:
            seen.add(key)
            result.append(row)
    return result
