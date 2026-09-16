import pytest

from scraper import ScraperError, WebScraper


class Response:
    text = ""
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.mark.parametrize("fail_closed", [False, True])
def test_robots_429_always_raises(monkeypatch, fail_closed):
    scraper = WebScraper("https://example.com", robots_fail_closed=fail_closed)
    monkeypatch.setattr(scraper.session, "get", lambda *args, **kwargs: Response(429))
    with pytest.raises(ScraperError, match="限流"):
        scraper._load_robots("https://example.com/robots.txt")


@pytest.mark.parametrize("status", [401, 403])
def test_robots_auth_errors_disallow(monkeypatch, status):
    scraper = WebScraper("https://example.com")
    monkeypatch.setattr(scraper.session, "get", lambda *args, **kwargs: Response(status))
    assert scraper._load_robots("https://example.com/robots.txt").can_fetch("*", "https://example.com/page") is False


def test_robots_404_allows(monkeypatch):
    scraper = WebScraper("https://example.com")
    monkeypatch.setattr(scraper.session, "get", lambda *args, **kwargs: Response(404))
    assert scraper._load_robots("https://example.com/robots.txt").can_fetch("*", "https://example.com/page") is True
