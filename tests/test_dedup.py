import unittest

from dedup import deduplicate


class TestDeduplicate(unittest.TestCase):
    def test_dedup_by_keys(self):
        data = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
            {"name": "Alice", "age": "31"},
        ]
        result = deduplicate(data, ["name"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Alice")
        self.assertEqual(result[1]["name"], "Bob")

    def test_dedup_whole_row(self):
        data = [
            {"name": "Alice", "age": "30"},
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        result = deduplicate(data)
        self.assertEqual(len(result), 2)

    def test_dedup_missing_field(self):
        """缺失字段应使用空字符串占位，不应产生相同 key。"""
        data = [
            {"name": "Alice", "age": "30"},
            {"name": "Alice"},
        ]
        result = deduplicate(data, ["name", "age"])
        self.assertEqual(len(result), 2)

    def test_dedup_empty_input(self):
        self.assertEqual(deduplicate([], ["name"]), [])


if __name__ == "__main__":
    unittest.main()
