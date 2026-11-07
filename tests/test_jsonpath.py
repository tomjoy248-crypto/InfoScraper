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

    def test_recursive_descent(self):
        data = {
            "a": {"name": "x"},
            "b": {"c": {"name": "y"}},
            "d": [{"name": "z"}],
        }
        self.assertEqual(query(data, "$..name"), ["x", "y", "z"])
        self.assertEqual(query(data, "..name"), ["x", "y", "z"])

    def test_filter_equal(self):
        data = {"items": [
            {"name": "a", "age": 30},
            {"name": "b", "age": 20},
        ]}
        result = query(data, "items[?(@.name == 'a')].age")
        self.assertEqual(result, [30])

    def test_filter_not_equal(self):
        data = {"items": [
            {"name": "a", "age": 30},
            {"name": "b", "age": 20},
        ]}
        result = query(data, "items[?(@.name != 'a')].age")
        self.assertEqual(result, [20])

    def test_filter_numeric_compare(self):
        data = {"items": [
            {"name": "a", "age": 30},
            {"name": "b", "age": 20},
            {"name": "c", "age": 25},
        ]}
        self.assertEqual(query(data, "items[?(@.age > 25)].name"), ["a"])
        self.assertEqual(query(data, "items[?(@.age >= 25)].name"), ["a", "c"])
        self.assertEqual(query(data, "items[?(@.age < 25)].name"), ["b"])
        self.assertEqual(query(data, "items[?(@.age <= 25)].name"), ["b", "c"])

    def test_filter_boolean(self):
        data = {"items": [
            {"name": "a", "active": True},
            {"name": "b", "active": False},
        ]}
        result = query(data, "items[?(@.active == true)].name")
        self.assertEqual(result, ["a"])

    def test_bracket_key_access(self):
        data = {"data-list": [{"中文名": "甲"}]}
        self.assertEqual(query(data, "$.data-list[*].中文名"), ["甲"])
        self.assertEqual(query(data, "$['data-list'][0]['中文名']"), ["甲"])


if __name__ == "__main__":
    unittest.main()
