"""Passive JavaScript and API endpoint discovery."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import urllib.error
from typing import Iterable, List


ENDPOINT_RE = re.compile(r"(?:https?://[^\"'\s<>]+|/(?:api|rest|graphql|v[0-9]+)/[A-Za-z0-9_./?=&:%-]*)", re.I)
SOURCE_MAP_RE = re.compile(r"//#\s*sourceMappingURL=([^\s]+)", re.I)


def script_urls(html: str, page_url: str) -> List[str]:
    values = []
    for raw in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I):
        target = urllib.parse.urljoin(page_url, raw)
        if urllib.parse.urlparse(target).hostname == urllib.parse.urlparse(page_url).hostname:
            values.append(target)
    return sorted(set(values))


def inspect_script(url: str, timeout: int = 10) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "InfoScraper/4.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read(4 * 1024 * 1024).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"script": url, "endpoints": [], "source_map": ""}
    endpoints = sorted(set(ENDPOINT_RE.findall(text)))
    source_map = ""
    match = SOURCE_MAP_RE.search(text)
    if match:
        source_map = urllib.parse.urljoin(url, match.group(1))
    return {"script": url, "endpoints": endpoints[:500], "source_map": source_map}


def inspect_scripts(html: str, page_url: str) -> List[dict]:
    return [inspect_script(url) for url in script_urls(html, page_url)]


def extract_html_endpoints(html: str, page_url: str) -> List[str]:
    """Find public API-like URLs in inline scripts and JSON config blocks."""
    values = set()
    for match in ENDPOINT_RE.findall(html):
        target = urllib.parse.urljoin(page_url, match)
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            values.add(target)
    return sorted(values)[:500]
