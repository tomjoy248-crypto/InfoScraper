"""URL 安全校验：拦截私有/回环/链路本地/保留地址，防止 SSRF。

除校验外，还提供“锁定 IP 建连”组件（PinnedHTTPConnection 等）：
先校验域名解析结果，再直接连接校验通过的 IP，TLS 握手仍使用
原始主机名做 SNI / 证书校验，从而消除校验与建连之间的
DNS rebinding（TOCTOU）窗口。
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.parse
import urllib.request


class UnsafeURLError(ValueError):
    """URL 解析到受保护地址或使用了不支持的协议。"""


def safe_ips(hostname: str, port: int = 443, trusted_hosts: set | None = None) -> list[str]:
    """解析并校验主机名，返回可安全连接的公网 IP 列表（去重）。

    trusted_hosts 中的域名豁免 IP 分类检查（仍需可解析）。
    """
    hostname = str(hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise UnsafeURLError("空主机名")
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"目标域名无法解析: {hostname}") from exc
    ips = list(dict.fromkeys(info[4][0] for info in infos))
    if not ips:
        raise UnsafeURLError(f"目标域名无法解析: {hostname}")
    trusted = {str(h).lower() for h in (trusted_hosts or set())}
    if hostname in trusted:
        return ips
    for value in ips:
        addr = ipaddress.ip_address(value)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise UnsafeURLError(f"目标解析到受保护地址 {value}")
    return ips


def validate_url(url: str, trusted_hosts: set | None = None) -> None:
    """校验 URL 的协议与目标地址，失败抛 UnsafeURLError。

    - 仅允许 http/https
    - 解析域名后，若任一 IP 属于私有/回环/链路本地/保留地址则拒绝
    - trusted_hosts 中的域名可豁免
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("仅支持 http/https URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    safe_ips(parsed.hostname, port, trusted_hosts)


class ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向 SSRF 防护：跳转目标也必须通过 url_guard 校验。

    公网站点可能 30x 跳转到内网/回环/保留地址（重定向型 SSRF），
    这里在每次跟随前校验 Location，解析到受保护地址时返回 None，
    urlopen 会抛出原始 30x HTTPError，由调用方记录而不发起请求。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_url(newurl)
        except UnsafeURLError:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _pinned_connect(conn: http.client.HTTPConnection, wrap_tls: bool) -> None:
    """校验目标并锁定已校验 IP 建连（DNS rebinding 防护核心）。

    校验与建连使用同一份解析结果（safe_ips 返回的 IP），
    攻击者无法在校验通过后、实际建连前切换 DNS 记录。
    """
    ips = safe_ips(conn.host, conn.port)
    create = getattr(conn, "_create_connection", None) or socket.create_connection
    last_error = None
    sock = None
    for ip in ips:
        try:
            sock = create((ip, conn.port), conn.timeout, conn.source_address)
            break
        except OSError as exc:
            last_error = exc
    if sock is None:
        raise last_error or OSError(f"无法连接: {conn.host}:{conn.port}")
    conn.sock = sock
    if conn._tunnel_host:
        conn._tunnel()
    if wrap_tls:
        # TLS SNI / 证书校验仍使用原始主机名，而非锁定的 IP
        conn.sock = conn._context.wrap_socket(conn.sock, server_hostname=conn.host)


class PinnedHTTPConnection(http.client.HTTPConnection):
    """连接前校验目标并锁定已校验的 IP。"""

    def connect(self):
        _pinned_connect(self, wrap_tls=False)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """同 PinnedHTTPConnection；TLS 握手使用原始主机名做 SNI / 证书校验。"""

    def connect(self):
        _pinned_connect(self, wrap_tls=True)


class PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(PinnedHTTPConnection, req)


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(PinnedHTTPSConnection, req, context=self._context)


def build_pinned_opener(*extra_handlers) -> urllib.request.OpenerDirector:
    """构建 SSRF 校验 + IP 锁定 opener，默认包含安全重定向校验。"""
    return urllib.request.build_opener(
        PinnedHTTPHandler(), PinnedHTTPSHandler(), ValidatingRedirectHandler(), *extra_handlers
    )
