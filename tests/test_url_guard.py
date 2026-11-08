"""url_guard IP 锁定建连（DNS rebinding / TOCTOU 防护）测试。"""

import pytest

import url_guard
from url_guard import UnsafeURLError, PinnedHTTPConnection, PinnedHTTPSConnection, safe_ips


def _fake_getaddrinfo(ips):
    def _resolve(host, port, type=None):
        return [(None, None, None, "", (ip, port)) for ip in ips]
    return _resolve


def test_safe_ips_rejects_protected_address(monkeypatch):
    monkeypatch.setattr(url_guard.socket, "getaddrinfo", _fake_getaddrinfo(["127.0.0.1"]))
    with pytest.raises(UnsafeURLError):
        safe_ips("evil.example.com")


def test_safe_ips_dedups_and_returns_public(monkeypatch):
    monkeypatch.setattr(
        url_guard.socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34", "93.184.216.34"])
    )
    assert safe_ips("example.com") == ["93.184.216.34"]


def test_safe_ips_trusted_host_bypasses_ip_check(monkeypatch):
    # 信任域豁免 IP 分类检查（如用户自己的内网采集目标）
    monkeypatch.setattr(url_guard.socket, "getaddrinfo", _fake_getaddrinfo(["10.0.0.5"]))
    assert safe_ips("intranet.local", trusted_hosts={"intranet.local"}) == ["10.0.0.5"]


def test_validate_url_scheme_check():
    with pytest.raises(UnsafeURLError):
        url_guard.validate_url("ftp://example.com/")


def test_pinned_connection_uses_validated_ip(monkeypatch):
    # 建连必须用 safe_ips 校验过的 IP，而不是再次解析主机名
    monkeypatch.setattr(url_guard, "safe_ips", lambda host, port=443, trusted_hosts=None: ["203.0.113.9"])
    conn = PinnedHTTPConnection("example.com", 80)
    targets = []

    def fake_create(address, timeout=None, source_address=None):
        targets.append(address)
        return object()

    monkeypatch.setattr(conn, "_create_connection", fake_create)
    conn.connect()
    assert targets == [("203.0.113.9", 80)]


def test_pinned_https_keeps_original_hostname_for_tls(monkeypatch):
    # TLS SNI / 证书校验使用原始主机名，而非锁定 IP
    monkeypatch.setattr(url_guard, "safe_ips", lambda host, port=443, trusted_hosts=None: ["203.0.113.9"])
    conn = PinnedHTTPSConnection("example.com", 443)
    monkeypatch.setattr(conn, "_create_connection", lambda a, timeout=None, source_address=None: object())

    class _RecordingContext:
        server_hostname = None

        def wrap_socket(self, sock, server_hostname=None):
            self.server_hostname = server_hostname
            return sock

    ctx = _RecordingContext()
    monkeypatch.setattr(conn, "_context", ctx)
    conn.connect()
    assert ctx.server_hostname == "example.com"


def test_pinned_connection_fails_before_connecting_to_protected(monkeypatch):
    # 校验失败时必须在建连前抛出，绝不发起 TCP 连接
    def _raise(host, port=443, trusted_hosts=None):
        raise UnsafeURLError("目标解析到受保护地址 127.0.0.1")

    monkeypatch.setattr(url_guard, "safe_ips", _raise)
    conn = PinnedHTTPConnection("example.com", 80)

    def _fail(address, timeout=None, source_address=None):
        raise AssertionError("不应发起任何连接")

    monkeypatch.setattr(conn, "_create_connection", _fail)
    with pytest.raises(UnsafeURLError):
        conn.connect()
