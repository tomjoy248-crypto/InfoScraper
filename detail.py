"""列表页 -> 详情页二级采集。

列表页负责产出“行 + 详情页链接”，详情页负责补齐正文类字段，
最终把两部分字段合并成一行。设计约束：

* 所有网络请求都走调用方传入的 ``fetch`` 回调，从而复用主爬虫的
  robots 校验、代理池、重试、渲染与取消能力。
* 纯解析逻辑（``parse_detail_fields``）不依赖网络，便于离线测试。
"""

import urllib.parse
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

from bs4 import BeautifulSoup, Tag


DEFAULT_URL_FIELD = "详情链接"
DEFAULT_DETAIL_LIST_SELECTOR = "body"


class DetailError(Exception):
    """详情页采集配置或解析异常。"""


def normalize_detail_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """校验并补全详情页配置，非法配置直接抛错而不是静默忽略。"""
    cfg = dict(config or {})
    fields = cfg.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise DetailError("详情页采集已启用，但未配置任何详情字段")
    cleaned = []
    for field in fields:
        if not isinstance(field, dict):
            raise DetailError("详情字段必须是对象")
        name = str(field.get("name") or "").strip()
        if not name:
            raise DetailError("详情字段缺少字段名")
        selector = str(field.get("selector") or "").strip()
        attr = str(field.get("attr") or "").strip() or None
        if not selector:
            raise DetailError(f"详情字段 {name} 缺少选择器")
        cleaned.append({"name": name, "selector": selector, "attr": attr})
    try:
        concurrency = int(cfg.get("concurrency") or 1)
    except (TypeError, ValueError):
        concurrency = 1
    return {
        "enabled": bool(cfg.get("enabled")),
        "url_field": str(cfg.get("url_field") or DEFAULT_URL_FIELD).strip() or DEFAULT_URL_FIELD,
        "list_selector": str(cfg.get("list_selector") or DEFAULT_DETAIL_LIST_SELECTOR).strip(),
        "selector_type": "xpath" if str(cfg.get("selector_type", "css")).lower() == "xpath" else "css",
        "fields": cleaned,
        "keep_list_fields": bool(cfg.get("keep_list_fields", True)),
        "skip_on_error": bool(cfg.get("skip_on_error", True)),
        "error_field": str(cfg.get("error_field") or "详情错误").strip() or "详情错误",
        "max_items": max(0, int(cfg.get("max_items") or 0)),
        "concurrency": max(1, min(concurrency, 16)),
    }


def absolute_url(base_url: str, raw: str) -> str:
    """把列表页里拿到的相对链接补全为绝对链接。"""
    value = (raw or "").strip()
    if not value or value.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    return urllib.parse.urljoin(base_url, value)


def resolve_detail_url(row: Dict[str, Any], base_url: str, url_field: str) -> str:
    raw = row.get(url_field, "")
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    return absolute_url(base_url, str(raw))


def _extract(element: Any, attr: Optional[str]) -> str:
    if attr:
        if hasattr(element, "get"):
            return (element.get(attr) or "").strip()
        return ""
    if isinstance(element, Tag):
        return element.get_text(strip=True)
    if hasattr(element, "text_content"):
        return element.text_content().strip()
    if hasattr(element, "text"):
        return element.text.strip()
    return str(element).strip()


def parse_detail_fields(
    html_text: str,
    fields: List[Dict[str, Any]],
    list_selector: str = DEFAULT_DETAIL_LIST_SELECTOR,
    selector_type: str = "css",
) -> Dict[str, str]:
    """从详情页 HTML 中提取字段。

    ``list_selector`` 用于限定取值范围：默认 ``body`` 让字段选择器直接
    相对整页匹配；填写 ``.content`` 这类容器时，字段选择器相对容器匹配。
    """
    result: Dict[str, str] = {}
    if selector_type == "xpath":
        from lxml import html as lh

        tree = lh.fromstring(html_text)
        scopes = tree.xpath(list_selector) if list_selector else [tree]
        for field in fields:
            selector = field.get("selector") or ""
            attr = field.get("attr")
            value = ""
            for scope in scopes:
                hits = scope.xpath(selector) if selector else []
                if not hits:
                    continue
                value = _extract(hits[0], attr)
                if value:
                    break
            result[field["name"]] = value
        return result

    soup = BeautifulSoup(html_text, "lxml")
    scopes = soup.select(list_selector) if list_selector else [soup]
    for field in fields:
        selector = field.get("selector") or ""
        attr = field.get("attr")
        value = ""
        for scope in scopes:
            hit = scope.select_one(selector) if selector and hasattr(scope, "select_one") else None
            if hit is None:
                continue
            value = _extract(hit, attr)
            if value:
                break
        result[field["name"]] = value
    return result


def merge_row(row: Dict[str, Any], detail: Dict[str, str], keep_list_fields: bool = True) -> Dict[str, Any]:
    """把详情字段合并进列表行；列表字段优先，避免详情页空值覆盖已有数据。"""
    if not keep_list_fields:
        merged: Dict[str, Any] = {}
    else:
        merged = dict(row)
    for key, value in detail.items():
        if keep_list_fields and merged.get(key) not in (None, ""):
            continue
        merged[key] = value
    return merged


def attach_details(
    rows: Iterable[Dict[str, Any]],
    fetch: Callable[[str], str],
    config: Dict[str, Any],
    base_url: str = "",
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    seen_urls: Optional[set] = None,
) -> Iterator[Dict[str, Any]]:
    """逐行抓取详情页并合并字段（流式，不缓存全量结果）。"""
    cfg = normalize_detail_config(config)
    url_field = cfg["url_field"]
    visited = seen_urls if seen_urls is not None else set()
    emitted = 0
    skipped = 0
    limit = cfg["max_items"]

    for row in rows:
        if should_stop and should_stop():
            break
        if limit and emitted >= limit:
            break
        if not isinstance(row, dict):
            continue
        detail_url = resolve_detail_url(row, base_url, url_field)
        if not detail_url:
            skipped += 1
            if on_log:
                on_log(f"未找到合法详情链接，保留列表数据: {list(row.values())[:1]}")
            emitted += 1
            yield row
            continue
        if detail_url in visited:
            if on_log:
                on_log(f"详情页重复，跳过请求: {detail_url}")
            emitted += 1
            yield row
            continue
        visited.add(detail_url)
        try:
            html_text = fetch(detail_url)
            detail = parse_detail_fields(
                html_text, cfg["fields"], cfg["list_selector"], cfg["selector_type"]
            )
            merged = merge_row(row, detail, cfg["keep_list_fields"])
        except Exception as exc:
            if not cfg["skip_on_error"]:
                raise
            merged = dict(row)
            merged[cfg["error_field"]] = str(exc)
            if on_log:
                on_log(f"详情页采集失败，已跳过 {detail_url}: {exc}")
        emitted += 1
        if on_progress:
            on_progress(emitted, skipped)
        yield merged
        if sleep:
            sleep(0)
