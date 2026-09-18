"""Low-risk, passive asset discovery primitives for authorized domains."""

from __future__ import annotations

import csv
import json
import socket
import urllib.parse
import urllib.request
import urllib.error
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Iterable, List


@dataclass
class Asset:
    value: str
    source: str
    kind: str = "subdomain"
    ip: str = ""
    status: str = ""
    fingerprint: str = ""
    security_headers: str = ""
    final_url: str = ""


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        value = urllib.parse.urlparse(value).hostname or ""
    return value.strip(".")


def resolve_host(host: str) -> List[str]:
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError:
        return []


def crtsh_subdomains(domain: str, timeout: int = 15) -> List[Asset]:
    query = urllib.parse.urlencode({"q": f"%.{domain}", "output": "json"})
    request = urllib.request.Request(
        f"https://crt.sh/?{query}", headers={"User-Agent": "InfoScraper/4.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        rows = json.loads(response.read().decode("utf-8", errors="replace"))
    assets = {}
    for row in rows:
        for name in str(row.get("name_value", "")).splitlines():
            host = normalize_domain(name.lstrip("*."))
            if host == domain or not host.endswith("." + domain):
                continue
            assets[host] = Asset(host, "crt.sh")
    return list(assets.values())


def enrich_dns(assets: Iterable[Asset]) -> List[Asset]:
    result = []
    for asset in assets:
        ips = resolve_host(asset.value)
        asset.ip = ",".join(ips)
        result.append(asset)
    return result


def probe_http(asset: Asset, timeout: int = 8) -> Asset:
    """Perform a single low-impact HTTP request and record basic metadata."""
    for scheme in ("https", "http"):
        url = f"{scheme}://{asset.value}/"
        request = urllib.request.Request(url, headers={"User-Agent": "InfoScraper/4.0"}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(256 * 1024).decode("utf-8", errors="replace")
                asset.final_url = response.geturl()
                title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
                title_text = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
                asset.status = f"{response.status} {title_text}".strip()
                signals = []
                server = (response.headers.get("Server") or "").lower()
                powered = (response.headers.get("X-Powered-By") or "").lower()
                headers = f"{server} {powered}".lower()
                for name, marker in (("Nginx", "nginx"), ("Apache", "apache"), ("IIS", "microsoft-iis"),
                                     ("PHP", "php"), ("ASP.NET", "asp.net")):
                    if marker in headers:
                        signals.append(name)
                page = body.lower()
                for name, marker in (("WordPress", "wp-content"), ("Laravel", "laravel_session"),
                                     ("Django", "csrfmiddlewaretoken"), ("Vue", "vue"), ("React", "react")):
                    if marker in page and name not in signals:
                        signals.append(name)
                asset.fingerprint = ", ".join(signals)
                expected = ("strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy")
                missing = [name for name in expected if not response.headers.get(name)]
                asset.security_headers = "missing: " + ", ".join(missing) if missing else "all common headers present"
                return asset
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        asset.status = "unreachable"
        asset.fingerprint = ""
    return asset


def discover_public_urls(domain: str, timeout: int = 10) -> List[Asset]:
    """Read public robots/sitemap files without crawling arbitrary paths."""
    base = f"https://{domain}/"
    discovered = {}
    for path, kind in (("robots.txt", "robots"), ("sitemap.xml", "sitemap")):
        try:
            request = urllib.request.Request(base + path, headers={"User-Agent": "InfoScraper/4.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
            urls = re.findall(r"(?im)^\s*(?:allow|disallow|sitemap):\s*(\S+)", text) if kind == "robots" else re.findall(r"<loc>(.*?)</loc>", text, re.I | re.S)
            for value in urls:
                value = urllib.parse.urljoin(base, value.strip())
                if value.startswith(("http://", "https://")):
                    discovered[value] = Asset(value, kind, "url")
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError):
            continue
    return list(discovered.values())


def export_assets(assets: Iterable[Asset], path: str) -> None:
    rows = [asdict(asset) for asset in assets]
    if path.lower().endswith(".json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["value", "source", "kind", "ip", "status"])
        writer.writeheader()
        writer.writerows(rows)
