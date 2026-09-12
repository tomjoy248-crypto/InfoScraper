import json
import os
from typing import Any, Dict


DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")


def ensure_config_dir():
    os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)


def save_task(name: str, task: Dict[str, Any]):
    ensure_config_dir()
    path = os.path.join(DEFAULT_CONFIG_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)


def load_task(name: str) -> Dict[str, Any]:
    path = os.path.join(DEFAULT_CONFIG_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_tasks() -> list:
    ensure_config_dir()
    names = []
    for f in os.listdir(DEFAULT_CONFIG_DIR):
        if f.endswith(".json"):
            names.append(f[:-5])
    return names
