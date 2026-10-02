from typing import Dict, List, Optional


class IncrementalDeduplicator:
    """Bounded-state deduplicator for streaming scraper output."""

    def __init__(self, keys: Optional[List[str]] = None):
        self.keys = keys
        self.seen = set()

    def accept(self, row: Dict[str, str]) -> bool:
        """Return True only for the first occurrence of a row."""
        if self.keys:
            key = tuple(str(row.get(k, "")).strip() for k in self.keys)
        else:
            key = tuple(sorted(row.items()))
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


def deduplicate(data: List[Dict[str, str]], keys: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """根据指定字段去重，未指定则按整行去重。保留第一次出现的记录。

    当指定字段在某些行中不存在时，使用空字符串占位，避免不同缺失字段组合产生相同 key。
    """
    seen = set()
    result = []
    for row in data:
        if keys:
            # 明确按顺序为每个 key 生成值，缺失字段用空字符串表示
            key = tuple(str(row.get(k, "")).strip() for k in keys)
        else:
            key = tuple(sorted(row.items()))
        if not key or key not in seen:
            seen.add(key)
            result.append(row)
    return result
