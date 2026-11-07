"""URL 安全校验：拦截私有/回环/链路本地/保留地址，防止 SSRF。

核心逻辑与 scraper.Scraper._validate_url 一致，但作为无状态函数供
recon_core / social 等非 Scraper 链路复用。
"""

import ipaddress
import socket
import urllib.parse


class UnsafeURLError(ValueError):
    """URL 解析到受保护地址或使用了不支持的协议。"""


def validate_url(url: str, trusted_hosts: set | None = None) -> None:
    """校验 URL 的协议与目标地址，失败抛 UnsafeURLError。

    - 仅允许 http/https
    - 解析域名后，若任一 IP 属于私有/回环/链路本地/保留地址则拒绝
    - trusted_hosts 中的域名可豁免
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("仅支持 http/https URL")
    hostname = parsed.hostname.lower()
    trusted = {h.lower() for h in (trusted_hosts or set())}
    if hostname in trusted:
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"目标域名无法解析: {hostname}") from exc
    ips = {info[4][0] for info in infos}
    if not ips:
        raise UnsafeURLError(f"目标域名无法解析: {hostname}")
    for value in ips:
        addr = ipaddress.ip_address(value)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise UnsafeURLError(f"目标解析到受保护地址 {value}")
