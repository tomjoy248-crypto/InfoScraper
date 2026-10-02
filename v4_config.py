"""Local configuration store for optional API integrations.

Secrets are kept in the user's application data directory with restrictive
permissions where supported; the UI should never write them to task JSON.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict
import secure_storage

SUPPORTED_PROVIDERS = ("fofa", "shodan", "virustotal", "securitytrails")


def validate_providers(values: Dict[str, str]) -> tuple[Dict[str, str], list[str]]:
    """Normalize provider keys and report obviously malformed entries."""
    clean = {}
    errors = []
    for name in SUPPORTED_PROVIDERS:
        value = str(values.get(name, "")).strip()
        if not value:
            continue
        if any(ch.isspace() for ch in value) or len(value) < 8:
            errors.append(f"{name.upper()} API Key 格式异常")
            continue
        clean[name] = value
    return clean, errors


def config_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "InfoScraper"
    root.mkdir(parents=True, exist_ok=True)
    return root / "providers.json"


def load_providers() -> Dict[str, str]:
    path = config_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {}
        result: Dict[str, str] = {}
        for key, item in value.items():
            try:
                result[str(key)] = secure_storage.decrypt(str(item))
            except Exception:
                # A config copied from another Windows account, or an older
                # encryption format, must not prevent the GUI from opening.
                continue
        return result
    except (OSError, ValueError, TypeError):
        return {}


def save_providers(values: Dict[str, str]) -> None:
    path = config_path()
    safe = {str(key): secure_storage.encrypt(str(value)) for key, value in values.items() if value}
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
