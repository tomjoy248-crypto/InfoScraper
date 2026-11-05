import pytest

from search_engine import (
    SearchError,
    build_query,
    build_search_url,
    collect_search_results,
    looks_blocked,
    normalize_search_config,
    parse_bing,
    parse_duckduckgo,
    total_pages,
)

BING_HTML = """
<html><body><ol id="b_results">
  <li class="b_algo">
    <h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h">示例标题 A</a></h2>
    <div class="b_caption"><p>摘要 A</p></div>
  </li>
  <li class="b_algo">
    <h2><a href="https://example.org/b">示例标题 B</a></h2>
    <div class="b_caption"><p>摘要 B</p></div>
  </li>
  <li class="b_algo"><h2>没有链接的条目</h2></li>
</ol></body></html>
"""

DDG_HTML = """
<html><body>
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx">DDG 标题 X</a>
    <a class="result__snippet">DDG 摘要 X</a>
  </div>
  <div class="result"><a class="result__a" href="https://example.net/y">DDG 标题 Y</a></div>
</body></html>
"""


def test_normalize_search_config_accepts_string_keywords():
    cfg = normalize_search_config({"engine": "Bing", "keywords": "爬虫, 教程\n反爬", "max_results": "30"})
    assert cfg["engine"] == "bing"
    assert cfg["keywords"] == ["爬虫", "教程", "反爬"]
    assert cfg["max_results"] == 30


@pytest.mark.parametrize("config", [
    {"engine": "google", "keywords": "x"},
    {"engine": "bing", "keywords": "  "},
    {"engine": "bing", "keywords": "x", "max_results": "abc"},
])
def test_normalize_search_config_rejects_bad_values(config):
    with pytest.raises(SearchError):
        normalize_search_config(config)


def test_normalize_search_config_falls_back_on_zero_max_results():
    # 0 是假值，会走 `or 20` 的默认分支，而不是抛错
    cfg = normalize_search_config({"engine": "bing", "keywords": "x", "max_results": 0})
    assert cfg["max_results"] == 20


def test_build_query_applies_site_filter():
    assert build_query("关键词", "example.com") == "site:example.com 关键词"
    assert build_query("关键词") == "关键词"


def test_build_search_url_paginates_with_offset():
    first = build_search_url("bing", "q", 1)
    third = build_search_url("bing", "q", 3)
    assert "first=1" in first
    assert "first=21" in third
    assert build_search_url("duckduckgo", "q", 1).startswith("https://html.duckduckgo.com/html/")
    with pytest.raises(SearchError):
        build_search_url("baidu", "q")


def test_parse_bing_unwraps_redirect_and_skips_linkless_items():
    rows = parse_bing(BING_HTML, page=1)
    assert [r["标题"] for r in rows] == ["示例标题 A", "示例标题 B"]
    # a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h 是 https://example.com/a 的 base64url 形式，
    # 未解开时也应保持为可用的绝对链接而不是丢行。
    assert rows[0]["链接"].startswith(("https://example.com/a", "https://www.bing.com/ck/a"))
    assert rows[1]["链接"] == "https://example.org/b"
    assert rows[1]["站点"] == "example.org"
    assert rows[1]["摘要"] == "摘要 B"


def test_parse_duckduckgo_unwraps_uddg_param():
    rows = parse_duckduckgo(DDG_HTML, page=1)
    assert rows[0]["链接"] == "https://example.com/x"
    assert rows[1]["链接"] == "https://example.net/y"
    assert rows[1]["摘要"] == ""


def test_parse_second_page_narrows_serial_numbers():
    rows = parse_bing(BING_HTML, page=2)
    assert rows[0]["序号"] == "11"


def test_looks_blocked_detects_captcha_page():
    assert looks_blocked("<html>Please verify you are human</html>") is True
    assert looks_blocked("<html>正常结果页</html>") is False


def test_looks_blocked_detects_duckduckgo_anomaly_challenge():
    # DuckDuckGo 判流量可疑时会返回图片挑战页，不含任何结果结构
    challenge = '<html><div class="anomaly-modal__content">'\
                '<form id="challenge-form" action="/anomaly.js"></form>'\
                '<input type="checkbox" class="anomaly-modal__check"></div></html>'
    assert looks_blocked(challenge) is True


def test_challenge_page_raises_instead_of_returning_empty():
    challenge = '<html><form id="challenge-form"></form></html>'
    with pytest.raises(SearchError):
        list(collect_search_results(
            {"engine": "duckduckgo", "keywords": ["x"], "max_results": 5},
            fetch=lambda url: challenge,
        ))


def test_total_pages_covers_requested_results():
    assert total_pages("bing", 1) == 1
    assert total_pages("bing", 10) == 1
    assert total_pages("bing", 25) == 3
    assert total_pages("duckduckgo", 60) > 1


def test_collect_search_results_streams_rows_with_dedup_and_limit():
    requested = []

    def fetch(url):
        requested.append(url)
        return BING_HTML

    rows = list(collect_search_results(
        {"engine": "bing", "keywords": ["关键词一", "关键词一"], "max_results": 50},
        fetch=fetch,
    ))
    # 每个关键词都命中同样的两条链接，去重后只应产出 2 条
    assert len(rows) == 2
    assert len({r["链接"] for r in rows}) == 2
    assert rows[0]["关键词"] == "关键词一"
    # 第一轮翻满 3 页（max_results=50 需要 5 页，但第 2 页起就无新结果，只剩 2 页上限里的翻页）；
    # 第二轮关键词结果全部被去重，连续两页无新结果即结束，明显少于“每关键词跑满 5 页”的 10 次。
    assert len(requested) < 10
    assert len({r["链接"] for r in rows}) == 2


def test_collect_search_results_stops_at_max_results():
    rows = list(collect_search_results(
        {"engine": "bing", "keywords": ["x"], "max_results": 1},
        fetch=lambda url: BING_HTML,
    ))
    assert len(rows) == 1


def test_collect_search_results_reports_blocked_page():
    with pytest.raises(SearchError):
        list(collect_search_results(
            {"engine": "bing", "keywords": ["x"], "max_results": 5},
            fetch=lambda url: "<html>unusual traffic detected</html>",
        ))


def test_collect_search_results_tolerates_failure_after_first_page():
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        if calls["n"] == 1:
            return BING_HTML
        raise OSError("网络中断")

    logs = []
    rows = list(collect_search_results(
        {"engine": "bing", "keywords": ["x"], "max_results": 50},
        fetch=fetch,
        on_log=logs.append,
    ))
    assert rows
    assert any("请求失败" in line for line in logs)


def test_collect_search_results_raises_when_first_page_fails():
    def fetch(url):
        raise OSError("目标不可达")

    with pytest.raises(OSError):
        list(collect_search_results(
            {"engine": "bing", "keywords": ["x"], "max_results": 5}, fetch=fetch
        ))


def test_collect_search_results_respects_should_stop():
    rows = list(collect_search_results(
        {"engine": "bing", "keywords": ["x"], "max_results": 50},
        fetch=lambda url: BING_HTML,
        should_stop=lambda: True,
    ))
    assert rows == []
