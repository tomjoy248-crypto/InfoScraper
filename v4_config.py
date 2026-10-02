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
        return {key: secure_storage.decrypt(str(item)) for key, item in value.items()}
    except (OSError, ValueError):
        return {}


def save_providers(values: Dict[str, str]) -> None:
    path = config_path()
    safe = {str(key): secure_storage.encrypt(str(value)) for key, value in values.items() if value}
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
