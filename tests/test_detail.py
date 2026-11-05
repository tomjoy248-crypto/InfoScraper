import pytest

from detail import (
    DetailError,
    absolute_url,
    attach_details,
    merge_row,
    normalize_detail_config,
    parse_detail_fields,
    resolve_detail_url,
)

DETAIL_HTML = """
<html><body>
  <div class="content">
    <h1 class="title">详情标题</h1>
    <div class="body">详情正文内容</div>
    <a class="next" href="/page2">下一页</a>
  </div>
</body></html>
"""

FIELDS = [
    {"name": "详情标题", "selector": "h1.title", "attr": None},
    {"name": "详情正文", "selector": ".body", "attr": None},
    {"name": "下一页", "selector": "a.next", "attr": "href"},
    {"name": "缺失字段", "selector": ".not-exist", "attr": None},
]


def test_normalize_detail_config_fills_defaults():
    cfg = normalize_detail_config({"enabled": True, "fields": FIELDS[:1]})
    assert cfg["url_field"] == "详情链接"
    assert cfg["list_selector"] == "body"
    assert cfg["selector_type"] == "css"
    assert cfg["keep_list_fields"] is True
    assert cfg["skip_on_error"] is True


@pytest.mark.parametrize("config", [
    {"fields": []},
    {"fields": [{"selector": ".x"}]},
    {"fields": [{"name": "缺选择器"}]},
    {"fields": ["不是对象"]},
])
def test_normalize_detail_config_rejects_bad_fields(config):
    with pytest.raises(DetailError):
        normalize_detail_config(config)


def test_absolute_url_skips_pseudo_links():
    assert absolute_url("https://example.com/list/", "item/1") == "https://example.com/list/item/1"
    assert absolute_url("https://example.com", "/a/b") == "https://example.com/a/b"
    for bad in ("javascript:void(0)", "#top", "mailto:a@b.com", "data:image/png;base64,xx", "  "):
        assert absolute_url("https://example.com", bad) == ""


def test_resolve_detail_url_handles_list_values():
    assert resolve_detail_url({"详情链接": "/article/1"}, "https://example.com/news/", "详情链接") == "https://example.com/article/1"
    assert resolve_detail_url({"详情链接": ["/a", "/b"]}, "https://example.com/", "详情链接") == "https://example.com/a"
    assert resolve_detail_url({}, "https://example.com/", "详情链接") == ""


def test_parse_detail_fields_extracts_text_and_attr():
    detail = parse_detail_fields(DETAIL_HTML, FIELDS)
    assert detail["详情标题"] == "详情标题"
    assert detail["详情正文"] == "详情正文内容"
    assert detail["下一页"] == "/page2"
    assert detail["缺失字段"] == ""


def test_parse_detail_fields_respects_scope_container():
    scoped = parse_detail_fields(DETAIL_HTML, FIELDS, list_selector=".content")
    assert scoped["详情正文"] == "详情正文内容"
    missing = parse_detail_fields(DETAIL_HTML, FIELDS, list_selector=".not-exist")
    assert missing["详情正文"] == ""


def test_parse_detail_fields_supports_xpath():
    fields = [
        {"name": "标题", "selector": "//h1[@class='title']/text()", "attr": None},
        {"name": "链接", "selector": "//a[@class='next']/@href", "attr": None},
    ]
    detail = parse_detail_fields(DETAIL_HTML, fields, list_selector="//div[@class='content']", selector_type="xpath")
    assert detail["链接"] == "/page2"


def test_merge_row_prefers_non_empty_list_values():
    row = {"标题": "列表标题", "作者": ""}
    merged = merge_row(row, {"标题": "详情标题", "作者": "张三"}, keep_list_fields=True)
    assert merged["标题"] == "列表标题"
    assert merged["作者"] == "张三"


def test_merge_row_can_drop_list_fields():
    merged = merge_row({"标题": "列表标题"}, {"正文": "内容"}, keep_list_fields=False)
    assert merged == {"正文": "内容"}


def test_attach_details_fetches_and_merges():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return DETAIL_HTML

    rows = [
        {"标题": "A", "详情链接": "/article/1"},
        {"标题": "B", "详情链接": "https://example.com/article/2"},
    ]
    out = list(attach_details(
        rows,
        fetch=fetch,
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}]},
        base_url="https://example.com/list/",
    ))
    assert [r["正文"] for r in out] == ["详情正文内容", "详情正文内容"]
    assert fetched == ["https://example.com/article/1", "https://example.com/article/2"]
    assert out[0]["标题"] == "A"


def test_attach_details_keeps_row_without_link():
    logs = []
    out = list(attach_details(
        [{"标题": "无链接"}],
        fetch=lambda url: pytest.fail("不应发起请求"),
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}]},
        base_url="https://example.com/",
        on_log=logs.append,
    ))
    assert out == [{"标题": "无链接"}]
    assert logs


def test_attach_details_records_error_when_skipping():
    out = list(attach_details(
        [{"标题": "A", "详情链接": "/1"}],
        fetch=lambda url: (_ for _ in ()).throw(OSError("超时")),
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}], "skip_on_error": True},
        base_url="https://example.com/",
    ))
    assert out[0]["标题"] == "A"
    assert "超时" in out[0]["详情错误"]


def test_attach_details_raises_when_skip_disabled():
    with pytest.raises(OSError):
        list(attach_details(
            [{"标题": "A", "详情链接": "/1"}],
            fetch=lambda url: (_ for _ in ()).throw(OSError("超时")),
            config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}], "skip_on_error": False},
            base_url="https://example.com/",
        ))


def test_attach_details_dedups_repeated_urls():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return DETAIL_HTML

    out = list(attach_details(
        [{"标题": "A", "详情链接": "/1"}, {"标题": "B", "详情链接": "/1"}],
        fetch=fetch,
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}]},
        base_url="https://example.com/",
    ))
    assert len(out) == 2
    assert fetched == ["https://example.com/1"]


def test_attach_details_honours_max_items_and_stop():
    out = list(attach_details(
        [{"详情链接": f"/{i}"} for i in range(5)],
        fetch=lambda url: DETAIL_HTML,
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}], "max_items": 2},
        base_url="https://example.com/",
    ))
    assert len(out) == 2

    stopped = list(attach_details(
        [{"详情链接": "/1"}],
        fetch=lambda url: pytest.fail("不应发起请求"),
        config={"enabled": True, "fields": [{"name": "正文", "selector": ".body"}]},
        base_url="https://example.com/",
        should_stop=lambda: True,
    ))
    assert stopped == []
