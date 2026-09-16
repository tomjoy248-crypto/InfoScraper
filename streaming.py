"""Streaming row processing pipeline shared by GUI and scheduled jobs."""

from typing import Dict, Iterable, Iterator, List, Optional

from cleaner import CLEAN_RULES
from dedup import IncrementalDeduplicator


def process_rows(rows: Iterable[Dict[str, str]], field_rules: Optional[Dict[str, List[str]]] = None,
                dedup_keys: Optional[List[str]] = None, known_keys: Optional[set] = None,
                dedup: bool = False
                ) -> Iterator[Dict[str, str]]:
    """Clean, filter, and deduplicate rows one at a time with bounded state."""
    rules = field_rules or {}
    deduper = IncrementalDeduplicator(None) if dedup and not dedup_keys else None
    # Copy the caller's set only when absent; when supplied, update it so a
    # single pipeline also suppresses duplicates encountered later in the same
    # run (and makes the contract explicit).
    known = known_keys if known_keys is not None else set()
    for row in rows:
        item = dict(row)
        for field, field_ruleset in rules.items():
            if field in item:
                for rule in field_ruleset:
                    if rule in CLEAN_RULES:
                        item[field] = CLEAN_RULES[rule](item[field])
        if dedup and dedup_keys:
            key = tuple(str(item.get(k, "")).strip() for k in dedup_keys)
            if key in known:
                continue
            known.add(key)
        if dedup and dedup_keys:
            yield item
        elif deduper is None or deduper.accept(item):
            yield item
