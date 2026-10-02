"""Read-only DNS record collection through DNS-over-HTTPS."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Dict, List


def query(name: str, record_type: str, timeout: int = 8) -> List[str]:
    params = urllib.parse.urlencode({"name": name, "type": record_type})
    request = urllib.request.Request(
        "https://cloudflare-dns.com/dns-query?" + params,
        headers={"Accept": "application/dns-json", "User-Agent": "InfoScraper/4.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return sorted({str(answer.get("data", "")).strip().rstrip(".") for answer in data.get("Answer", []) if answer.get("data")})
    except Exception:
        return []


def collect(domain: str) -> Dict[str, List[str]]:
    return {record_type: query(domain, record_type) for record_type in ("A", "AAAA", "CNAME", "MX", "NS", "TXT")}
