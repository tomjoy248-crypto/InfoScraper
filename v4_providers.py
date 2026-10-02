"""Read-only adapters for optional external asset data providers."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def _get(url: str, headers: dict[str, str], timeout: int = 12) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def shodan_host(ip: str, api_key: str, timeout: int = 12) -> dict[str, Any]:
    if not api_key.strip():
        return {"ok": False, "error": "未配置 Shodan API Key", "items": []}
    try:
        data = _get(f"https://api.shodan.io/shodan/host/{urllib.parse.quote(ip)}?key={urllib.parse.quote(api_key)}", {}, timeout)
        return {"ok": True, "provider": "shodan", "items": [data]}
    except Exception as exc:
        return {"ok": False, "provider": "shodan", "error": str(exc), "items": []}


def virustotal_domain(domain: str, api_key: str, timeout: int = 12) -> dict[str, Any]:
    if not api_key.strip():
        return {"ok": False, "error": "未配置 VirusTotal API Key", "items": []}
    try:
        data = _get(f"https://www.virustotal.com/api/v3/domains/{urllib.parse.quote(domain)}", {"x-apikey": api_key}, timeout)
        return {"ok": True, "provider": "virustotal", "items": [data]}
    except Exception as exc:
        return {"ok": False, "provider": "virustotal", "error": str(exc), "items": []}


def securitytrails_subdomains(domain: str, api_key: str, timeout: int = 12) -> dict[str, Any]:
    if not api_key.strip():
        return {"ok": False, "error": "未配置 SecurityTrails API Key", "items": []}
    try:
        data = _get(f"https://api.securitytrails.com/v1/domain/{urllib.parse.quote(domain)}/subdomains", {"apikey": api_key}, timeout)
        names = [f"{name}.{domain}" for name in data.get("subdomains", []) if name]
        return {"ok": True, "provider": "securitytrails", "items": sorted(set(names))}
    except Exception as exc:
        return {"ok": False, "provider": "securitytrails", "error": str(exc), "items": []}


def fofa_search(query: str, api_key: str, email: str = "", timeout: int = 12) -> dict[str, Any]:
    if not api_key.strip() or not email.strip():
        return {"ok": False, "provider": "fofa", "error": "FOFA 需要 API Key 和邮箱", "items": []}
    try:
        token = __import__("base64").b64encode(f"{email}:{api_key}".encode()).decode()
        encoded = __import__("base64").b64encode(query.encode()).decode()
        data = _get(f"https://fofa.info/api/v1/search/all?key={urllib.parse.quote(api_key)}&qbase64={encoded}&size=100", {"Authorization": f"Basic {token}"}, timeout)
        return {"ok": bool(data.get("error") is not True), "provider": "fofa", "items": data.get("results", []), "error": data.get("errmsg", "")}
    except Exception as exc:
        return {"ok": False, "provider": "fofa", "error": str(exc), "items": []}
