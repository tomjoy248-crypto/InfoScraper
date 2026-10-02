"""Bounded, authorized asset-assessment workflow orchestration."""

from __future__ import annotations

from threading import Event
from typing import Callable, Dict, List

from recon_core import (crtsh_subdomains, discover_public_urls, enrich_dns,
                        enrich_network, hackertarget_subdomains, probe_http)
from v4_executor import run_checks


def run_full(domain: str, allowed_host: str = "", max_ports: bool = False,
             cancelled: Event | None = None,
             on_progress: Callable[[str], None] | None = None) -> Dict[str, List[dict]]:
    """Run passive discovery and optional allowlisted TCP checks."""
    cancelled = cancelled or Event()
    log = on_progress or (lambda _message: None)
    log("查询被动子域名数据源")
    discovered = {item.value: item for item in crtsh_subdomains(domain)}
    for item in hackertarget_subdomains(domain):
        discovered.setdefault(item.value, item)
    if cancelled.is_set():
        return {}
    log(f"发现 {len(discovered)} 个子域名，开始 DNS/IP 解析")
    assets = [probe_http(enrich_network(item)) for item in enrich_dns(discovered.values())]
    urls = discover_public_urls(domain)
    result = {
        "assets": [item.__dict__ for item in assets],
        "public_urls": [item.__dict__ for item in urls],
        "ports": [],
    }
    if max_ports and allowed_host and allowed_host.lower() in {domain.lower(), *(item.value.lower() for item in assets)}:
        log("开始授权主机常见端口检查")
        ports = (21, 22, 25, 53, 80, 443, 3306, 5432, 6379, 8080, 8443)
        result["ports"] = [item.__dict__ for item in run_checks([(allowed_host, port) for port in ports], cancelled=cancelled)]
    log("一键资产流程完成")
    return result
