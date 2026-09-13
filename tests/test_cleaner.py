import unittest

from cleaner import apply_clean_rules


class TestCleaner(unittest.TestCase):
    def test_strip(self):
        data = [{"title": "  Hello  "}]
        result = apply_clean_rules(data, {"title": ["strip"]})
        self.assertEqual(result[0]["title"], "Hello")

    def test_remove_html(self):
        data = [{"desc": "<p>Hello</p>"}]
        result = apply_clean_rules(data, {"desc": ["remove_html"]})
        self.assertEqual(result[0]["desc"], "Hello")

    def test_extract_number(self):
        data = [{"price": "Price: $12.5"}]
        result = apply_clean_rules(data, {"price": ["extract_number"]})
        self.assertEqual(result[0]["price"], "12.5")

    def test_extract_email(self):
        data = [{"contact": "contact me at foo@example.com or bar@test.org"}]
        result = apply_clean_rules(data, {"contact": ["extract_email"]})
        self.assertEqual(result[0]["contact"], "foo@example.com, bar@test.org")

    def test_multiple_rules(self):
        data = [{"title": "  <b>Hello</b>  "}]
        result = apply_clean_rules(data, {"title": ["remove_html", "strip", "to_lower"]})
        self.assertEqual(result[0]["title"], "hello")


if __name__ == "__main__":
    unittest.main()
