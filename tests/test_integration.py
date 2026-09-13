"""Offline integration checks for HTTP parsing and proxy selection."""

from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

from scraper import WebScraper
from cancellation import CancellationToken


def test_api_session_request_and_json():
    scraper = WebScraper("https://example.com", mode="api")
    response = Mock(status_code=200)
    response.json.return_value = {"data": [{"id": 1}]}
    response.raise_for_status.return_value = None
    with patch("scraper.socket.gethostbyname", return_value="93.184.216.34"), patch.object(scraper.session, "get", return_value=response) as request:
        assert scraper._fetch_api("https://example.com/api")["data"][0]["id"] == 1
        request.assert_called_once()


def test_proxy_health_failure_is_safe():
    from database import check_proxy
    with patch("requests.get", side_effect=OSError("offline")):
        assert check_proxy("http://127.0.0.1:9", timeout=0.01) is False


def test_cancel_interrupts_wait():
    scraper = WebScraper("https://example.com")
    scraper.cancel()
    assert scraper._should_stop() is True


def test_shared_cancellation_token():
    token = CancellationToken()
    scraper = WebScraper("https://example.com", cancellation_token=token)
    token.cancel()
    assert scraper._should_stop() is True


def test_real_local_http_fetch():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><div class='item'><span>ok</span></div></html>"
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    scraper = WebScraper(f"http://127.0.0.1:{server.server_port}")
    # Bypass SSRF protection only for this isolated local test server.
    with patch.object(scraper, "_validate_url"):
        html = scraper._fetch(scraper.start_url)
    server.shutdown()
    assert "ok" in html
