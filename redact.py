"""Utilities for preventing Cookie/token leakage in logs and exports."""

import re
from typing import Any


def redact_text(value: str) -> str:
    """Mask common Cookie and bearer-token values in text."""
    value = re.sub(r"(?i)(cookie|authorization|token|api[_-]?key|password|passwd|secret)(\s*[:=]\s*)[^;\s,]+", r"\1\2[REDACTED]", value)
    value = re.sub(r"(?i)(https?://[^\s/@]+):[^\s/@]+@", r"\1:[REDACTED]@", value)
    return value


def redact(value: Any) -> Any:
    """Recursively redact sensitive mapping keys."""
    if isinstance(value, dict):
        sensitive = {"cookie", "authorization", "token", "access_token", "api_key", "password", "passwd", "secret", "proxy"}
        return {k: ("[REDACTED]" if str(k).lower() in sensitive else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return redact_text(value) if isinstance(value, str) else value
