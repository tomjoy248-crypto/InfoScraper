import pytest
import jsonpath


def test_unicode_and_hyphen_keys():
    data = {"data-list": [{"中文名": "甲"}]}
    assert jsonpath.query(data, "$.data-list[*].中文名") == ["甲"]


def test_invalid_jsonpath_is_not_silent():
    with pytest.raises(jsonpath.JSONPathError):
        jsonpath.query({"a": 1}, "$.a.@bad")
