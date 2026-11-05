"""搜索引擎结果采集（Bing / DuckDuckGo HTML 版，无需 API Key）。

只解析公开结果页的标题、链接、摘要和站点，便于做公开信息收集。
不涉及验证码绕过或登录态滥用；结果页被反爬拦截时会直接报错而不是循环重试。
"""

import html as html_lib
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


SUPPORTED_ENGINES = ("bing", "duckduckgo")

ENGINE_LABELS = {
    "bing": "Bing",
    "duckduckgo": "DuckDuckGo",
}

BING_HOST = "https://www.bing.com"
DUCKDUCKGO_HOST = "https://html.duckduckgo.com"

BING_PAGE_SIZE = 10
DUCKDUCKGO_PAGE_SIZE = 25


class SearchError(Exception):
    """搜索引擎结果采集异常。"""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


def normalize_search_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """校验搜索配置，非法值直接返回错误而不是静默降级。"""
    cfg = dict(config or {})
    engine = str(cfg.get("engine") or "bing").lower()
    if engine not in SUPPORTED_ENGINES:
        raise SearchError(f"不支持的搜索引擎: {engine}（可选 {', '.join(SUPPORTED_ENGINES)}）")
    keywords = cfg.get("keywords") or []
    if isinstance(keywords, str):
        keywords = re.split(r"[\n,，;；]+", keywords)
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    if not keywords:
        raise SearchError("请至少填写一个搜索关键词")
    try:
        max_results = int(cfg.get("max_results") or 20)
    except (TypeError, ValueError):
        raise SearchError("最大结果数必须是整数")
    if max_results < 1:
        raise SearchError("最大结果数必须大于 0")
    site = str(cfg.get("site") or "").strip()
    return {
        "engine": engine,
        "keywords": keywords,
        "max_results": max_results,
        "site": site,
        "lang": str(cfg.get("lang") or "").strip(),
        "region": str(cfg.get("region") or "").strip(),
    }


def build_query(keyword: str, site: str = "") -> str:
    """组合关键词与站点限定，如 ``site:example.com 关键词``。"""
    keyword = (keyword or "").strip()
    if site:
        return f"site:{site} {keyword}".strip()
    return keyword


def build_search_url(engine: str, query: str, page: int = 1, lang: str = "", region: str = "") -> str:
    """构造结果页 URL。``page`` 从 1 开始。"""
    page = max(1, int(page))
    if engine == "bing":
        offset = (page - 1) * BING_PAGE_SIZE + 1
        params = {"q": query, "first": str(offset)}
        if region:
            params["cc"] = region
        if lang:
            params["setlang"] = lang
        return f"{BING_HOST}/search?{urllib.parse.urlencode(params)}"
    if engine == "duckduckgo":
        params = {"q": query}
        if region:
            params["kl"] = region
        if page > 1:
            # DuckDuckGo 使用 POST 翻页，GET 形式仅支持首页；
            # 这里用 s 参数保持向后兼容，解析失败时会自然结束。
            params["s"] = str((page - 1) * DUCKDUCKGO_PAGE_SIZE)
        return f"{DUCKDUCKGO_HOST}/html/?{urllib.parse.urlencode(params)}"
    raise SearchError(f"不支持的搜索引擎: {engine}")


def _absolute(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    return value


def _strip_redirect(href: str) -> str:
    """解开 Bing / DuckDuckGo 的跳转包装，拿到真实目标地址。"""
    href = _absolute(href)
    if not href:
        return ""
    parsed = urllib.parse.urlparse(href)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "u", "uddg", "target"):
        if key in query and query[key]:
            candidate = query[key][0]
            candidate = urllib.parse.unquote(candidate)
            if candidate.startswith("//"):
                return "https:" + candidate
            if candidate.startswith(("http://", "https://")):
                return candidate
    return href


def _host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""


def parse_bing(html_text: str, page: int = 1) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text, "lxml")
    rows: List[Dict[str, str]] = []
    index = (page - 1) * BING_PAGE_SIZE
    for li in soup.select("li.b_algo"):
        link = li.select_one("h2 a[href]") or li.select_one("a[href]")
        if link is None:
            continue
        url = _strip_redirect(link.get("href", ""))
        if not url.startswith(("http://", "https://")):
            continue
        title = _clean_text(link.get_text(" ", strip=True))
        snippet_node = li.select_one(".b_caption p") or li.select_one("p")
        snippet = _clean_text(snippet_node.get_text(" ", strip=True)) if snippet_node else ""
        index += 1
        rows.append({
            "序号": str(index),
            "搜索引擎": ENGINE_LABELS["bing"],
            "标题": title,
            "链接": url,
            "站点": _host_of(url),
            "摘要": snippet,
            "关键词": "",
        })
    return rows


def parse_duckduckgo(html_text: str, page: int = 1) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text, "lxml")
    rows: List[Dict[str, str]] = []
    index = (page - 1) * DUCKDUCKGO_PAGE_SIZE
    for block in soup.select("div.result, div.web-result"):
        link = block.select_one("a.result__a[href]") or block.select_one("a[href]")
        if link is None:
            continue
        url = _strip_redirect(link.get("href", ""))
        if not url.startswith(("http://", "https://")):
            continue
        title = _clean_text(link.get_text(" ", strip=True))
        snippet_node = block.select_one(".result__snippet") or block.select_one("a.result__snippet")
        snippet = _clean_text(snippet_node.get_text(" ", strip=True)) if snippet_node else ""
        index += 1
        rows.append({
            "序号": str(index),
            "搜索引擎": ENGINE_LABELS["duckduckgo"],
            "标题": title,
            "链接": url,
            "站点": _host_of(url),
            "摘要": snippet,
            "关键词": "",
        })
    return rows


def parse_results(engine: str, html_text: str, page: int = 1) -> List[Dict[str, str]]:
    if engine == "bing":
        return parse_bing(html_text, page)
    if engine == "duckduckgo":
        return parse_duckduckgo(html_text, page)
    raise SearchError(f"不支持的搜索引擎: {engine}")


def looks_blocked(html_text: str) -> bool:
    """识别明显的验证码/拦截页，避免把空结果当成“已采完”。

    搜索引擎在判定流量可疑时会返回不含结果结构的挑战页（如 DuckDuckGo 的
    ``anomaly-modal`` 图片挑战、Bing 的验证码页）。这类页面若不识别，会被
    误判成“0 条结果”，让用户以为关键词真的没有搜索结果。
    """
    lowered = (html_text or "").lower()
    signals = (
        "captcha",
        "unusual traffic",
        "verify you are human",
        "访问过于频繁",
        "人机验证",
        "anomaly-modal",
        "challenge-form",
        "challenge-submit",
    )
    return any(signal in lowered for signal in signals)


def page_size(engine: str) -> int:
    return BING_PAGE_SIZE if engine == "bing" else DUCKDUCKGO_PAGE_SIZE


def total_pages(engine: str, max_results: int) -> int:
    """根据目标条数推算需要翻多少页。"""
    size = page_size(engine)
    return max(1, (int(max_results) + size - 1) // size)


def collect_search_results(
    config: Dict[str, Any],
    fetch,
    on_log=None,
    on_progress=None,
    should_stop=None,
    sleep=None,
    seen_urls: Optional[set] = None,
):
    """流式产出搜索结果行。

    ``fetch(url) -> str`` 由调用方提供，复用主爬虫的代理、重试与 robots 策略。
    """
    cfg = normalize_search_config(config)
    engine = cfg["engine"]
    visited = seen_urls if seen_urls is not None else set()
    produced = 0
    empty_pages = 0
    max_pages = total_pages(engine, cfg["max_results"])

    for keyword in cfg["keywords"]:
        query = build_query(keyword, cfg["site"])
        if on_log:
            on_log(f"[{ENGINE_LABELS[engine]}] 搜索: {query}")
        empty_pages = 0
        for page in range(1, max_pages + 1):
            if should_stop and should_stop():
                return
            if produced >= cfg["max_results"]:
                return
            url = build_search_url(engine, query, page, cfg["lang"], cfg["region"])
            if on_log:
                on_log(f"请求结果页第 {page} 页: {url}")
            try:
                html_text = fetch(url)
            except Exception as exc:
                # 单页失败不应中断整轮采集；但首页就失败说明目标不可达，需要报错。
                if produced == 0:
                    raise
                if on_log:
                    on_log(f"第 {page} 页请求失败，结束该关键词: {exc}")
                break
            if looks_blocked(html_text):
                raise SearchError(
                    f"{ENGINE_LABELS[engine]} 返回了验证码/可疑流量拦截页，"
                    "请降低采集频率、更换出口 IP 或稍后重试"
                )
            rows = parse_results(engine, html_text, page)
            page_produced = 0
            for row in rows:
                if produced >= cfg["max_results"]:
                    return
                key = row.get("链接", "")
                if not key or key in visited:
                    continue
                visited.add(key)
                row["关键词"] = keyword
                produced += 1
                page_produced += 1
                yield row
                if on_progress:
                    on_progress(produced, cfg["max_results"])
            # 无结果、或整页都被去重（关键词重复时常见），都视为空页并提前结束，
            # 避免把剩余页数白白请求一遍。
            if page_produced:
                empty_pages = 0
            else:
                empty_pages += 1
                if empty_pages >= 2:
                    if on_log:
                        on_log("连续两页无新结果，结束该关键词")
                    break
            if sleep:
                sleep(0)
