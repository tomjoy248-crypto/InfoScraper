"""Utilities for preventing Cookie/token leakage in logs and exports."""

import re
from typing import Any


def redact_text(value: str) -> str:
    """Mask common Cookie and bearer-token values in text."""
    value = re.sub(r"(?i)(cookie|authorization|token)(\s*[:=]\s*)[^;\s,]+", r"\1\2[REDACTED]", value)
    return value


def redact(value: Any) -> Any:
    """Recursively redact sensitive mapping keys."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if str(k).lower() in {"cookie", "authorization", "token"} else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return redact_text(value) if isinstance(value, str) else value
