import json

import checkpoint
from scraper import WebScraper


def test_checkpoint_roundtrip(tmp_path):
    path = str(tmp_path / "job.json")
    checkpoint.save(path, {"page": 3, "url": "https://example.com?p=3", "cursor": "abc"})
    assert checkpoint.load(path)["page"] == 3
    assert checkpoint.load(path)["cursor"] == "abc"


def test_checkpoint_invalid_file_returns_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    assert checkpoint.load(str(path)) == {}


def test_api_page_pagination_checkpoint(tmp_path):
    path = str(tmp_path / "page.json")
    scraper = WebScraper("https://example.com?page=1", mode="api", api_config={"pagination_type": "param", "pagination_param": "page"}, checkpoint_path=path)
    seen = []
    scraper._fetch_api = lambda url: seen.append(url) or [{"id": len(seen)}]
    assert len(scraper.run("$", [{"name": "id", "json_path": "id"}], max_pages=2)) == 2
    assert seen[-1].endswith("page=2")


def test_api_offset_pagination_checkpoint(tmp_path):
    path = str(tmp_path / "offset.json")
    scraper = WebScraper("https://example.com?offset=0", mode="api", api_config={"pagination_type": "offset", "offset_param": "offset", "offset_step": 10}, checkpoint_path=path)
    seen = []; scraper._fetch_api = lambda url: seen.append(url) or [{"id": 1}]
    scraper.run("$", [{"name": "id", "json_path": "id"}], max_pages=2)
    assert seen[-1].endswith("offset=10")


def test_api_cursor_and_next_url_pagination(tmp_path):
    for cfg, responses, expected in [
        ({"cursor_path": "next", "cursor_param": "cursor"}, [{"items": [{"id": 1}], "next": "abc"}, {"items": [{"id": 2}], "next": "def"}], "cursor=abc"),
        ({"next_url_path": "next"}, [{"items": [{"id": 1}], "next": "/p2"}, {"items": [{"id": 2}]}], "/p2"),
    ]:
        scraper = WebScraper("https://example.com", mode="api", api_config=cfg, checkpoint_path=str(tmp_path / "x.json"))
        seen = []; scraper._fetch_api = lambda url: seen.append(url) or responses[min(len(seen)-1, 1)]
        scraper.run("items", [{"name": "id", "json_path": "id"}], max_pages=2)
        assert expected in seen[-1]
