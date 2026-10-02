"""Bounded, authorized asset-assessment workflow orchestration."""

from __future__ import annotations

from threading import Event
from typing import Callable, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from recon_core import (crtsh_subdomains, discover_public_urls, enrich_dns,
                        enrich_network, hackertarget_subdomains, probe_http, Asset)
from v4_executor import run_checks
from v4_dns import collect as collect_dns


def run_full(domain: str, allowed_host: str = "", max_ports: bool = False,
             cancelled: Event | None = None,
             on_progress: Callable[[str], None] | None = None) -> Dict[str, List[dict]]:
    """Run passive discovery and optional allowlisted TCP checks."""
    cancelled = cancelled or Event()
    log = on_progress or (lambda _message: None)
    log("查询被动子域名数据源")
    # Always assess the host the user entered, even when passive sources return
    # no subdomains. Otherwise a perfectly valid small site produces an empty
    # asset table and appears broken.
    discovered = {domain: Asset(domain, "input")}
    try:
        discovered.update({item.value: item for item in crtsh_subdomains(domain)})
    except Exception as exc:
        log(f"crt.sh 数据源失败，已跳过: {exc}")
    try:
        for item in hackertarget_subdomains(domain):
            discovered.setdefault(item.value, item)
    except Exception as exc:
        log(f"Hackertarget 数据源失败，已跳过: {exc}")
    if cancelled.is_set():
        return {}
    log(f"发现 {len(discovered)} 个子域名，开始 DNS/IP 解析")
    assets = []
    try:
        enriched = enrich_dns(discovered.values())
    except Exception as exc:
        log(f"DNS 解析批次失败，改用未解析主机继续: {exc}")
        enriched = list(discovered.values())
    def inspect(item):
        try:
            return probe_http(enrich_network(item))
        except Exception as exc:
            log(f"主机 {item.value} 探测失败，已保留主机记录: {exc}")
            return item
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(enriched)))) as pool:
        futures = [pool.submit(inspect, item) for item in enriched]
        for future in as_completed(futures):
            assets.append(future.result())
    try:
        urls = discover_public_urls(domain)
    except Exception as exc:
        log(f"robots/sitemap 查询失败，已跳过: {exc}")
        urls = []
    try:
        dns = collect_dns(domain)
    except Exception as exc:
        log(f"DNS 查询失败，已跳过: {exc}")
        dns = {}
    result = {
        "assets": [item.__dict__ for item in assets],
        "public_urls": [item.__dict__ for item in urls],
        "dns": dns,
        "ports": [],
    }
    if max_ports and allowed_host and allowed_host.lower() in {domain.lower(), *(item.value.lower() for item in assets)}:
        log("开始授权主机常见端口检查")
        ports = (21, 22, 25, 53, 80, 443, 3306, 5432, 6379, 8080, 8443)
        try:
            result["ports"] = [item.__dict__ for item in run_checks([(allowed_host, port) for port in ports], cancelled=cancelled)]
        except Exception as exc:
            log(f"端口检查失败，已跳过: {exc}")
    log("一键资产流程完成")
    return result
