"""recon_core 重定向 SSRF 防护回归测试（M-1 残余修复）。"""

import urllib.error
import urllib.request

import recon_core
from recon_core import Asset, _ValidatingRedirectHandler


def test_redirect_to_protected_address_is_blocked():
    # 重定向型 SSRF：公网站点 30x 跳到回环/链路本地地址时必须拒绝跟随
    handler = _ValidatingRedirectHandler()
    req = urllib.request.Request("https://public.example.com/")
    assert handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/admin") is None
    assert handler.redirect_request(req, None, 302, "Found", {}, "http://169.254.169.254/latest/meta-data/") is None
    assert handler.redirect_request(req, None, 302, "Found", {}, "http://10.0.0.1/") is None


def test_redirect_to_public_address_is_followed(monkeypatch):
    # 校验通过时正常委托给默认重定向逻辑
    monkeypatch.setattr(recon_core, "validate_url", lambda url, trusted_hosts=None: None)
    handler = _ValidatingRedirectHandler()
    req = urllib.request.Request("https://public.example.com/")
    result = handler.redirect_request(req, None, 302, "Found", {}, "https://other.example.com/")
    assert isinstance(result, urllib.request.Request)
    assert result.full_url == "https://other.example.com/"


def test_probe_http_marks_blocked_redirect(monkeypatch):
    # opener 抛出 302 时，资产应记录 redirect blocked 而不是 unreachable
    monkeypatch.setattr(recon_core, "validate_url", lambda url, trusted_hosts=None: None)

    class _StubOpener:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 302, "Found", {}, None)

    monkeypatch.setattr(recon_core, "_SAFE_OPENER", _StubOpener())
    asset = recon_core.probe_http(Asset("example.com", "test"), delay=0)
    assert asset.status == "302 redirect blocked"
    assert asset.final_url == "https://example.com/"
