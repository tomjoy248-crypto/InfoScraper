from scraper import WebScraper
from subdomain import load_wordlist


def test_robots_is_enabled_by_default():
    scraper = WebScraper("https://example.com")
    assert scraper.respect_robots is True


def test_custom_subdomain_wordlist(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("www\n# comment\nAPI\n\n", encoding="utf-8")
    assert load_wordlist(str(path)) == ["www", "api"]
