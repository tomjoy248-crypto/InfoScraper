import unittest

from jsonpath import query


class TestJSONPath(unittest.TestCase):
    def test_root(self):
        data = {"name": "Alice"}
        self.assertEqual(query(data, ""), [data])
        self.assertEqual(query(data, "$"), [data])

    def test_simple_property(self):
        data = {"name": "Alice", "age": 30}
        self.assertEqual(query(data, "name"), ["Alice"])
        self.assertEqual(query(data, "age"), [30])
        self.assertEqual(query(data, "$.name"), ["Alice"])

    def test_nested_property(self):
        data = {"user": {"name": "Alice", "email": "a@example.com"}}
        self.assertEqual(query(data, "user.name"), ["Alice"])
        self.assertEqual(query(data, "$.user.email"), ["a@example.com"])

    def test_list_index(self):
        data = {"items": ["a", "b", "c"]}
        self.assertEqual(query(data, "items[0]"), ["a"])
        self.assertEqual(query(data, "items[2]"), ["c"])

    def test_list_wildcard(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        self.assertEqual(query(data, "items[*].name"), ["a", "b"])

    def test_missing_key(self):
        data = {"name": "Alice"}
        self.assertEqual(query(data, "age"), [])


if __name__ == "__main__":
    unittest.main()
