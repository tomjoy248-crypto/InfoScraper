import unittest

from scraper import WebScraper


class TestScraper(unittest.TestCase):
    def test_parse_fields_css(self):
        html = """
        <html><body>
        <div class="item"><h2>Title 1</h2><span class="price">10</span></div>
        <div class="item"><h2>Title 2</h2><span class="price">20</span></div>
        </body></html>
        """
        scraper = WebScraper(start_url="http://example.com")
        rows = scraper.parse_fields(
            html,
            list_selector=".item",
            fields=[
                {"name": "title", "selector": "h2"},
                {"name": "price", "selector": ".price"},
            ],
            selector_type="css",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "Title 1")
        self.assertEqual(rows[1]["price"], "20")

    def test_parse_fields_xpath(self):
        html = """
        <html><body>
        <div class="item"><h2>Title 1</h2></div>
        <div class="item"><h2>Title 2</h2></div>
        </body></html>
        """
        scraper = WebScraper(start_url="http://example.com")
        rows = scraper.parse_fields(
            html,
            list_selector="//div[@class='item']",
            fields=[{"name": "title", "selector": ".//h2/text()"}],
            selector_type="xpath",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "Title 1")

    def test_parse_api_items(self):
        data = {
            "data": {
                "items": [
                    {"name": "Alice", "age": 30},
                    {"name": "Bob", "age": 25},
                ]
            }
        }
        scraper = WebScraper(start_url="http://api.example.com", mode="api")
        rows = scraper.parse_api_items(
            data,
            list_path="data.items[*]",
            fields=[
                {"name": "name", "json_path": "name"},
                {"name": "age", "json_path": "age"},
            ],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Alice")
        self.assertEqual(rows[1]["age"], "25")

    def test_build_page_url(self):
        scraper = WebScraper(start_url="http://example.com")
        url = scraper._build_page_url("http://example.com?page=1", "page", 3)
        self.assertEqual(url, "http://example.com?page=3")

    def test_parse_cookies(self):
        scraper = WebScraper(start_url="http://example.com")
        cookies = scraper._parse_cookies("a=1; b=2")
        self.assertEqual(cookies, {"a": "1", "b": "2"})


if __name__ == "__main__":
    unittest.main()
