"""Crash-safe checkpoint persistence for resumable scrape jobs."""

import json
import os
from typing import Any, Dict


def load(path: str) -> Dict[str, Any]:
    """Load a checkpoint, returning an empty state when absent or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save(path: str, state: Dict[str, Any]) -> None:
    """Atomically save checkpoint state."""
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
