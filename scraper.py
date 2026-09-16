import json
import os
import copy
import random
import re
import time
import urllib.parse
import ipaddress
import socket
import urllib.robotparser
import io
import time
import checkpoint
from cancellation import CancellationToken
from typing import Any, Callable, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag
from lxml import html as lh

import jsonpath


USER_AGENT_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.86 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.85 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.84 Safari/537.36",
]


class ScraperError(Exception):
    """爬虫运行异常"""
    pass


class WebScraper:
    """通用网页爬虫：支持静态请求、CSS/XPath 解析、API 请求、翻页、反爬策略。"""

    def __init__(
        self,
        start_url: str,
        mode: str = "static",  # static | api
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[str] = None,
        timeout: int = 30,
        delay: float = 0.5,
        delay_random: bool = True,
        proxy: Optional[str] = None,
        proxy_pool: Optional[List[str]] = None,
        random_ua: bool = False,
        retries: int = 2,
        render: bool = False,
        api_config: Optional[Dict[str, Any]] = None,
        checkpoint_path: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
        respect_robots: bool = True,
        robots_fail_closed: bool = False,
        login_handler: Optional[Callable[[Any], bool]] = None,
        render_wait_until: str = "domcontentloaded",
    ):
        self.start_url = start_url
        self.mode = mode
        self.headers = headers or {}
        self.cookies = self._parse_cookies(cookies)
        self.timeout = timeout
        self.delay = delay
        self.delay_random = delay_random
        self.proxy_single = proxy
        self.proxy_pool = proxy_pool or []
        self.random_ua = random_ua
        self.retries = retries
        self.render = render
        self.api_config = api_config or {}
        self.checkpoint_path = checkpoint_path
        self.cancellation_token = cancellation_token or CancellationToken()
        self.login_handler = login_handler
        self.render_wait_until = render_wait_until if render_wait_until in {"domcontentloaded", "load", "networkidle"} else "domcontentloaded"
        self.respect_robots = respect_robots
        self.robots_fail_closed = robots_fail_closed
        self._resolved_hosts: Dict[str, str] = {}
        self._robots_cache = {}
        self.robots_cache_ttl = 3600
        self.robots_cache_limit = 100
        if self.checkpoint_path:
            os.makedirs(os.path.dirname(self.checkpoint_path) or ".", exist_ok=True)
        self._cancelled = False
        self._on_row: Optional[Callable[[Dict[str, str]], None]] = None
        # Prefer curl_cffi for browser-like TLS fingerprints; fall back to
        # requests when the optional native dependency is unavailable.
        try:
            from curl_cffi import requests as curl_requests
            self.session = curl_requests.Session(impersonate="chrome131")
        except (ImportError, TypeError) as exc:
            import logging
            logging.getLogger(__name__).warning("curl_cffi 不可用，降级使用 requests: %s", exc)
            self.session = requests.Session()
        self._update_headers()
        if self.cookies:
            self.session.cookies.update(self.cookies)
        self._playwright_page = None
        self._pw = None
        self._browser = None

    def _update_headers(self):
        base = {"User-Agent": random.choice(USER_AGENT_POOL) if self.random_ua else USER_AGENT_POOL[0]}
        base.update(self.headers)
        if self.mode == "api":
            base.setdefault("Accept", "application/json")
        self.session.headers.clear()
        self.session.headers.update(base)

    def _pick_proxy(self) -> Optional[Dict[str, str]]:
        if self.proxy_single:
            return {"http": self.proxy_single, "https": self.proxy_single}
        if self.proxy_pool:
            p = random.choice(self.proxy_pool)
            return {"http": p, "https": p}
        return None

    @staticmethod
    def _parse_cookies(cookie_str: Optional[str]) -> Dict[str, str]:
        if not cookie_str:
            return {}
        cookies = {}
        for part in cookie_str.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def cancel(self):
        """标记任务取消，当前正在进行的请求不会立即停止，但翻页循环会中断。"""
        self._cancelled = True
        self.cancellation_token.cancel()
        # Closing the session interrupts requests blocked on network I/O.
        try:
            self.session.close()
        except Exception:
            pass

    def set_row_callback(self, callback: Optional[Callable[[Dict[str, str]], None]]) -> None:
        """Set a callback invoked for every parsed row during streaming runs."""
        self._on_row = callback

    def _emit_rows(self, rows: List[Dict[str, str]], target: List[Dict[str, str]]) -> None:
        """Emit rows to a consumer while retaining compatibility with list callers."""
        if self._on_row:
            for row in rows:
                self._on_row(row)
        target.extend(rows)

    def _should_stop(self) -> bool:
        return self._cancelled or self.cancellation_token.is_cancelled()

    def _save_checkpoint(self, state: Dict[str, Any]) -> None:
        if not self.checkpoint_path:
            return
        try:
            checkpoint.save(self.checkpoint_path, state)
        except OSError as exc:
            import logging
            logging.getLogger(__name__).warning("断点保存失败（不影响本次采集）: %s", exc)

    def _sleep_interruptibly(self, seconds: float) -> None:
        """Sleep in short intervals so cancellation is responsive."""
        deadline = time.monotonic() + max(0.0, seconds)
        while not self._should_stop():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self.cancellation_token.wait(min(0.2, remaining)):
                return

    def _fetch(self, url: str, method: str = "GET", payload: Optional[Dict] = None) -> str:
        self._validate_url(url)
        if self.respect_robots and method.upper() == "GET":
            robots_url = urllib.parse.urljoin(url, "/robots.txt")
            self._validate_url(robots_url)
            rp = self._load_robots(robots_url)
            if not rp.can_fetch(self.session.headers.get("User-Agent", "*"), url):
                raise ScraperError("robots.txt 禁止采集该 URL")
        if self._should_stop():
            raise ScraperError("请求已取消")
        if self.render:
            return self._fetch_render(url)
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                proxies = self._pick_proxy()
                if method.upper() == "POST":
                    resp = self.session.post(
                        url, data=payload, proxies=proxies, timeout=self.timeout, allow_redirects=False
                    )
                else:
                    resp = self.session.get(url, proxies=proxies, timeout=self.timeout, allow_redirects=False)
                resp.raise_for_status()
                if self._should_stop():
                    raise ScraperError("请求已取消")
            except Exception as e:
                if isinstance(e, ScraperError):
                    raise
                last_error = e
                if self.random_ua:
                    self._update_headers()
                if attempt < self.retries:
                    self._sleep_interruptibly(random.uniform(1, 3))
            else:
                return resp.text
        raise ScraperError(f"请求失败（重试 {self.retries} 次）: {last_error}")

    def _load_robots(self, robots_url: str):
        cached = self._robots_cache.get(robots_url)
        if cached is not None:
            created, policy = cached
            if time.monotonic() - created < self.robots_cache_ttl:
                return policy
            self._robots_cache.pop(robots_url, None)
        rp = urllib.robotparser.RobotFileParser(); rp.set_url(robots_url)
        try:
            resp = self.session.get(robots_url, proxies=self._pick_proxy(), timeout=self.timeout, allow_redirects=False)
            code = getattr(resp, "status_code", 200)
            if code in (401, 403): rp.disallow_all = True
            elif code == 429: raise ScraperError("robots.txt 请求被限流，已停止采集")
            elif code >= 400: rp.allow_all = True
            else: rp.parse((getattr(resp, "text", "") or "").splitlines())
        except Exception as exc:
            if isinstance(exc, ScraperError):
                raise
            if self.robots_fail_closed:
                raise ScraperError(f"无法读取 robots.txt，已停止采集: {exc}") from exc
            import logging
            logging.getLogger(__name__).warning("robots.txt 读取失败，按放行处理: %s", exc)
            rp.allow_all = True
        if len(self._robots_cache) >= self.robots_cache_limit:
            self._robots_cache.pop(next(iter(self._robots_cache)))
        self._robots_cache[robots_url] = (time.monotonic(), rp)
        return rp

    def _validate_url(self, url: str) -> None:
        """Reject dangerous schemes and private/link-local destinations."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ScraperError("仅支持 http/https URL")
        try:
            first_all = {r[4][0] for r in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
            second_all = {r[4][0] for r in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
            if first_all != second_all or not first_all:
                raise ScraperError("DNS 解析结果不稳定，已阻止请求")
            first = sorted(first_all)[0]
            locked = self._resolved_hosts.get(parsed.hostname)
            if locked and locked != first:
                raise ScraperError("目标地址发生变化，已阻止可能的 DNS 重绑定")
            self._resolved_hosts[parsed.hostname] = first
            for value in first_all:
                address = ipaddress.ip_address(value)
                if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                    raise ScraperError("出于安全原因，禁止访问内网或本机地址")
        except socket.gaierror:
            pass

    def _fetch_api(self, url: str) -> Any:
        """API 模式请求，返回解析后的 JSON。"""
        self._validate_url(url)
        if self._should_stop():
            raise ScraperError("请求已取消")
        cfg = self.api_config
        if cfg.get("stream_prefix") and (cfg.get("next_url_path") or cfg.get("cursor_path")):
            raise ScraperError("流式模式不支持 next_url / cursor 分页，请改用 param/offset 分页")
        method = (cfg.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ScraperError(f"不支持的 API 请求方法: {method}")
        extra_headers = cfg.get("headers") or {}
        body = cfg.get("body")
        body_type = cfg.get("body_type", "json")
        if body_type not in {"json", "form"}:
            raise ScraperError(f"不支持的 API 请求体类型: {body_type}")
        if not isinstance(extra_headers, dict):
            raise ScraperError("API 额外请求头必须是 JSON 对象")

        last_error = None
        for attempt in range(self.retries + 1):
            try:
                proxies = self._pick_proxy()
                req_headers = dict(self.session.headers)
                req_headers.update(extra_headers)

                request_body = copy.deepcopy(body)
                # Allow pagination values to be placed in a JSON/form body.
                page_key = cfg.get("request_page_param")
                if page_key and isinstance(request_body, dict):
                    request_body[page_key] = cfg.get("request_page_value", 1)
                request_options = {"headers": req_headers, "proxies": proxies, "timeout": self.timeout, "allow_redirects": False}
                if cfg.get("stream_prefix"):
                    request_options["stream"] = True
                if method == "POST":
                    if body_type == "json":
                        req_headers.setdefault("Content-Type", "application/json")
                        resp = self.session.post(
                            url,
                            json=request_body, **request_options,
                        )
                    else:
                        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
                        resp = self.session.post(
                            url,
                            data=request_body, **request_options,
                        )
                else:
                    resp = self.session.get(url, **request_options)
                resp.raise_for_status()
                if self._should_stop():
                    raise ScraperError("请求已取消")
                if cfg.get("stream_prefix"):
                    return self._wrap_stream(self.iter_json_response(resp, cfg["stream_prefix"]))
                return resp.json()
            except ValueError as e:
                raise ScraperError(f"API 响应不是有效 JSON: {e}") from e
            except Exception as e:
                try:
                    import ijson
                    if isinstance(e, ijson.JSONError):
                        raise ScraperError(f"API 流式响应不是有效 JSON: {e}") from e
                except ImportError:
                    pass
                if isinstance(e, ScraperError):
                    raise
                last_error = e
                last_error = e
                if self.proxy_single and attempt == self.retries:
                    self.proxy_single = None
                if self.proxy_pool and attempt == self.retries:
                    failed = proxies.get("http") if proxies else None
                    self.proxy_pool = [p for p in self.proxy_pool if p != failed]
                if self.random_ua:
                    self._update_headers()
                if attempt < self.retries:
                    self._sleep_interruptibly(random.uniform(1, 3))
        raise ScraperError(f"API 请求失败（重试 {self.retries} 次）: {last_error}")

    @staticmethod
    def _wrap_stream(gen):
        try:
            yield from gen
        except Exception as exc:
            if isinstance(exc, ScraperError):
                raise
            raise ScraperError(f"API 流式响应解析失败: {exc}") from exc

    @staticmethod
    def iter_json_response(response, prefix="item"):
        """Stream a JSON array from a requests response when ijson is available."""
        try:
            import ijson
            raw = getattr(response, "raw", None)
            if raw is None:
                chunks = getattr(response, "iter_content", None)
                if chunks:
                    content = b"".join(chunks(chunk_size=65536))
                else:
                    content = getattr(response, "content", b"") or b""
                raw = io.BytesIO(content)
            try:
                yield from ijson.items(raw, prefix)
            finally:
                close = getattr(response, "close", None)
                if close: close()
        except ImportError:
            data = response.json()
            yield from (data if isinstance(data, list) else [])

    def _fetch_render(self, url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ScraperError("未安装 Playwright，请先执行: playwright install chromium")
        if self._playwright_page is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._playwright_page = self._browser.new_page()
            if self.cookies:
                domain = urllib.parse.urlparse(url).netloc
                prefix = "." if len(domain.split(".")) > 1 else ""
                self._playwright_page.context.add_cookies(
                    [
                        {"name": k, "value": v, "domain": prefix + domain, "path": "/"}
                        for k, v in self.cookies.items()
                    ]
                )
        last_error = None
        for attempt in range(self.retries + 1):
            if self._should_stop():
                raise ScraperError("请求已取消")
            try:
                if self._should_stop():
                    raise ScraperError("页面操作已取消")
                self._playwright_page.goto(url, wait_until=self.render_wait_until, timeout=self.timeout * 1000)
                if self._should_stop():
                    raise ScraperError("页面操作已取消")
                content = self._playwright_page.content()
                lowered = content.lower()
                if any(marker in lowered for marker in ("captcha", "verify you are human", "验证码")):
                    raise ScraperError("检测到验证码页面")
                if any(marker in lowered for marker in ("login", "sign in", "登录")) and self.cookies:
                    if self.login_handler and self.login_handler(self._playwright_page):
                        continue
                    raise ScraperError("可能登录失效，请重新提供 Cookie")
                return content
            except Exception as exc:
                last_error = exc
                self.close()
                if attempt < self.retries:
                    time.sleep(min(2.0, 0.5 * (attempt + 1)))
                    self._pw = sync_playwright().start()
                    self._browser = self._pw.chromium.launch(headless=True)
                    self._playwright_page = self._browser.new_page()
        raise ScraperError(f"页面渲染失败（重试 {self.retries} 次）: {last_error}") from last_error

    def close(self):
        try:
            if self._playwright_page:
                self._playwright_page.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._playwright_page = None
            self._browser = None
            self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _extract_field(element: Any, attr: Optional[str] = None) -> str:
        if attr:
            if isinstance(element, BeautifulSoup):
                return element.get(attr, "")
            return element.get(attr, "") if hasattr(element, "get") else ""
        text = ""
        if isinstance(element, Tag):
            text = element.get_text(strip=True)
        elif hasattr(element, "text_content"):
            text = element.text_content().strip()
        elif hasattr(element, "text"):
            text = element.text.strip()
        return text

    def parse_fields(
        self,
        html_text: str,
        list_selector: str,
        fields: List[Dict[str, Any]],
        selector_type: str = "css",
    ) -> List[Dict[str, str]]:
        results = []
        if selector_type == "css":
            soup = BeautifulSoup(html_text, "lxml")
            items = soup.select(list_selector)
            for item in items:
                row = {}
                for field in fields:
                    name = field["name"]
                    sel = field.get("selector", "")
                    attr = field.get("attr")
                    sub = item.select_one(sel) if sel else None
                    row[name] = self._extract_field(sub, attr) if sub else ""
                results.append(row)
        else:  # xpath
            tree = lh.fromstring(html_text)
            items = tree.xpath(list_selector)
            for item in items:
                row = {}
                for field in fields:
                    name = field["name"]
                    sel = field.get("selector", "")
                    attr = field.get("attr")
                    subs = item.xpath(sel) if sel else []
                    if not subs:
                        row[name] = ""
                        continue
                    sub = subs[0]
                    if attr:
                        row[name] = sub.get(attr, "") if hasattr(sub, "get") else ""
                    else:
                        row[name] = sub.text_content().strip() if hasattr(sub, "text_content") else str(sub)
                results.append(row)
        return results

    def parse_api_items(
        self,
        data: Any,
        list_path: str,
        fields: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """API 模式下解析 JSON 数据。"""
        items = jsonpath.query(data, list_path)
        results = []
        for item in items:
            if not isinstance(item, (dict, list)):
                continue
            row = {}
            for field in fields:
                name = field["name"]
                path = field.get("json_path") or field.get("selector", "")
                vals = jsonpath.query(item, path)
                if not vals:
                    row[name] = ""
                else:
                    v = vals[0]
                    row[name] = "" if v is None else str(v)
            results.append(row)
        return results

    def run(
        self,
        list_selector: str,
        fields: List[Dict[str, Any]],
        selector_type: str = "css",
        max_pages: int = 1,
        next_page_selector: Optional[str] = None,
        next_page_mode: str = "url",  # url | param
        next_page_param: str = "page",
        next_page_step: int = 1,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, str]]:
        if self.mode == "api":
            result = self._run_api(
                list_selector=list_selector,
                fields=fields,
                max_pages=max_pages,
                on_progress=on_progress,
                on_log=on_log,
            )
            if self.checkpoint_path and not self._cancelled:
                try:
                    os.remove(self.checkpoint_path)
                except OSError:
                    pass
            return result
        result = self._run_static(
            list_selector=list_selector,
            fields=fields,
            selector_type=selector_type,
            max_pages=max_pages,
            next_page_selector=next_page_selector,
            next_page_mode=next_page_mode,
            next_page_param=next_page_param,
            next_page_step=next_page_step,
            on_progress=on_progress,
            on_log=on_log,
        )
        if self.checkpoint_path and not self._cancelled:
            try:
                os.remove(self.checkpoint_path)
            except OSError:
                pass
        return result

    def iter_run(self, list_selector: str, fields: List[Dict[str, Any]], **kwargs):
        """Yield parsed rows incrementally without retaining the full result set."""
        if self.mode == "api":
            # API responses are decoded as a page at a time; rows are yielded
            # immediately even though the HTTP response itself is page-based.
            yield from self._iter_api(list_selector, fields, **kwargs)
            return
        yield from self._iter_static(list_selector, fields, **kwargs)

    def _iter_static(self, list_selector, fields, selector_type="css", max_pages=1,
                     next_page_selector=None, next_page_mode="url",
                     next_page_param="page", next_page_step=1,
                     on_progress=None, on_log=None):
        current_url = self.start_url
        state = checkpoint.load(self.checkpoint_path) if self.checkpoint_path else {}
        resume_page = int(state.get("page", 0)) + 1 if state else 1
        if state.get("url"):
            current_url = state["url"]
        page_start = self._guess_page_param_start(current_url, next_page_param)
        emitted = int(state.get("count", 0)) if state else 0
        for page in range(resume_page, max_pages + 1):
            if self._should_stop():
                if on_log: on_log("任务已取消")
                break
            if on_log: on_log(f"正在采集第 {page} 页: {current_url}")
            html_text = self._fetch(current_url)
            rows = self.parse_fields(html_text, list_selector, fields, selector_type)
            for row in rows:
                if self._should_stop(): break
                emitted += 1
                yield row
            if self.checkpoint_path:
                self._save_checkpoint({"page": page, "url": current_url, "count": emitted})
            if on_progress: on_progress(page, emitted)
            if page >= max_pages or self._should_stop(): break
            if next_page_mode == "param":
                current_url = self._build_page_url(current_url, next_page_param,
                                                   page_start + page * next_page_step)
            elif next_page_selector:
                next_a = BeautifulSoup(html_text, "lxml").select_one(next_page_selector)
                if not next_a or not next_a.get("href"): break
                current_url = urllib.parse.urljoin(current_url, next_a["href"])
            else: break
            self._sleep_interruptibly(self.delay + (random.uniform(0, self.delay) if self.delay_random else 0))

    def _iter_api(self, list_selector, fields, **kwargs):
        """Page-level API generator; emits each parsed row as soon as its page arrives."""
        cfg = self.api_config; ptype = cfg.get("pagination_type", "none")
        if cfg.get("stream_prefix") and (cfg.get("next_url_path") or cfg.get("cursor_path")):
            raise ScraperError("流式模式不支持 next_url / cursor 分页，请改用 param/offset 分页")
        max_pages = kwargs.get("max_pages", 1); on_progress = kwargs.get("on_progress"); on_log = kwargs.get("on_log")
        url = self.start_url; state = checkpoint.load(self.checkpoint_path) if self.checkpoint_path else {}
        start = int(state.get("page", 0)) + 1 if state else 1
        if state.get("url"): url = state["url"]
        total = int(state.get("count", 0)) if state else 0
        for page in range(start, max_pages + 1):
            if self._should_stop(): break
            if ptype in ("param", "offset"):
                key = cfg.get("pagination_param", "page") if ptype == "param" else cfg.get("offset_param", "offset")
                step = cfg.get("pagination_step", 1) if ptype == "param" else cfg.get("offset_step", 20)
                cfg["request_page_value"] = (1 if ptype == "param" else 0) + (page - 1) * step
            data = self._fetch_api(url)
            if cfg.get("stream_prefix"):
                for item in data:
                    if self._should_stop(): break
                    for row in self.parse_api_items([item], "$", fields):
                        total += 1; yield row
                data = None
            else:
                for row in self.parse_api_items(data, list_selector, fields):
                    total += 1; yield row
            if self.checkpoint_path: self._save_checkpoint({"page": page, "url": url, "count": total})
            if on_progress: on_progress(page, total)
            if page >= max_pages: break
            path = cfg.get("next_url_path"); cpath = cfg.get("cursor_path")
            if data is None and (path or cpath):
                break
            if path:
                vals = jsonpath.query(data, path)
                if not vals or not vals[0]: break
                url = urllib.parse.urljoin(url, str(vals[0]))
            elif cpath:
                vals = jsonpath.query(data, cpath)
                if not vals or vals[0] in (None, ""): break
                url = self._build_page_url(url, cfg.get("cursor_param", "cursor"), str(vals[0]))
            elif ptype in ("param", "offset"):
                key = cfg.get("pagination_param", "page") if ptype == "param" else cfg.get("offset_param", "offset")
                step = cfg.get("pagination_step", 1) if ptype == "param" else cfg.get("offset_step", 20)
                url = self._build_page_url(url, key, (1 if ptype == "param" else 0) + page * step)
            else: break
            self._sleep_interruptibly(self.delay)

    def _run_static(
        self,
        list_selector: str,
        fields: List[Dict[str, Any]],
        selector_type: str,
        max_pages: int,
        next_page_selector: Optional[str],
        next_page_mode: str,
        next_page_param: str,
        next_page_step: int,
        on_progress: Optional[Callable[[int, int], None]],
        on_log: Optional[Callable[[str], None]],
    ) -> List[Dict[str, str]]:
        all_results: List[Dict[str, str]] = []
        current_url = self.start_url
        page_param_start = self._guess_page_param_start(current_url, next_page_param)
        state = checkpoint.load(self.checkpoint_path) if self.checkpoint_path else {}
        resume_page = int(state.get("page", 0)) + 1 if state else 1
        if state.get("url"):
            current_url = state["url"]

        for page in range(resume_page, max_pages + 1):
            if self._should_stop():
                if on_log:
                    on_log("任务已取消")
                break
            if on_log:
                on_log(f"正在采集第 {page} 页: {current_url}")
            html_text = self._fetch(current_url)
            rows = self.parse_fields(html_text, list_selector, fields, selector_type)
            self._emit_rows(rows, all_results)
            if self.checkpoint_path:
                self._save_checkpoint({"page": page, "url": current_url, "count": len(all_results)})
            if on_progress:
                on_progress(page, len(all_results))
            if page >= max_pages:
                break

            # 下一页
            if next_page_mode == "param":
                current_url = self._build_page_url(
                    current_url, next_page_param, page_param_start + page * next_page_step
                )
            elif next_page_selector:
                soup = BeautifulSoup(html_text, "lxml")
                next_a = soup.select_one(next_page_selector)
                if not next_a or not next_a.get("href"):
                    if on_log:
                        on_log("未找到下一页，结束采集")
                    break
                current_url = urllib.parse.urljoin(current_url, next_a["href"])
            else:
                break
            sleep_time = self.delay + (random.uniform(0, self.delay) if self.delay_random else 0)
            self._sleep_interruptibly(sleep_time)
        return all_results

    def _run_api(
        self,
        list_selector: str,
        fields: List[Dict[str, Any]],
        max_pages: int,
        on_progress: Optional[Callable[[int, int], None]],
        on_log: Optional[Callable[[str], None]],
    ) -> List[Dict[str, str]]:
        cfg = self.api_config
        pagination_type = cfg.get("pagination_type", "none")
        pagination_param = cfg.get("pagination_param", "page")
        pagination_step = cfg.get("pagination_step", 1)
        offset_param = cfg.get("offset_param", "offset")
        offset_step = cfg.get("offset_step", 20)
        cursor_path = cfg.get("cursor_path")
        next_url_path = cfg.get("next_url_path")
        cursor_param = cfg.get("cursor_param", "cursor")

        all_results: List[Dict[str, str]] = []
        current_url = self.start_url

        page_param_start = 1
        offset_start = 0
        if pagination_type == "param":
            page_param_start = self._guess_page_param_start(current_url, pagination_param)
        elif pagination_type == "offset":
            offset_start = self._guess_offset_start(current_url, offset_param)

        state = checkpoint.load(self.checkpoint_path) if self.checkpoint_path else {}
        resume_page = int(state.get("page", 0)) + 1 if state else 1
        if state.get("url"):
            current_url = state["url"]
        for page in range(resume_page, max_pages + 1):
            if self._should_stop():
                if on_log:
                    on_log("任务已取消")
                break
            if on_log:
                on_log(f"正在请求 API 第 {page} 页: {current_url}")

            # Keep URL and body pagination in sync for APIs that page via POST.
            if pagination_type == "param":
                self.api_config["request_page_value"] = page_param_start + (page - 1) * pagination_step
            elif pagination_type == "offset":
                self.api_config["request_page_value"] = offset_start + (page - 1) * offset_step
            data = self._fetch_api(current_url)
            if cfg.get("stream_prefix"):
                for item in data:
                    for row in self.parse_api_items([item], "$", fields):
                        self._emit_rows([row], all_results)
            else:
                rows = self.parse_api_items(data, list_selector, fields)
                self._emit_rows(rows, all_results)
            if self.checkpoint_path:
                self._save_checkpoint({"page": page, "url": current_url, "count": len(all_results)})
            if on_progress:
                on_progress(page, len(all_results))
            if page >= max_pages:
                break

            # 下一页
            if next_url_path:
                next_urls = jsonpath.query(data, next_url_path)
                if next_urls and next_urls[0]:
                    current_url = urllib.parse.urljoin(current_url, str(next_urls[0]))
                else:
                    if on_log:
                        on_log("响应中未找到下一页 URL，结束采集")
                    break
            elif cursor_path:
                cursors = jsonpath.query(data, cursor_path)
                if not cursors or cursors[0] in (None, ""):
                    if on_log:
                        on_log("响应中未找到下一页游标，结束采集")
                    break
                current_url = self._build_page_url(current_url, cursor_param, str(cursors[0]))
            elif pagination_type == "param":
                next_value = page_param_start + page * pagination_step
                current_url = self._build_page_url(current_url, pagination_param, next_value)
            elif pagination_type == "offset":
                next_value = offset_start + page * offset_step
                current_url = self._build_page_url(current_url, offset_param, next_value)
            else:
                if on_log:
                    on_log("未配置 API 翻页，结束采集")
                break

            sleep_time = self.delay + (random.uniform(0, self.delay) if self.delay_random else 0)
            self._sleep_interruptibly(sleep_time)
        return all_results

    @staticmethod
    def _guess_page_param_start(url: str, param: str) -> int:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if param in qs:
            try:
                return int(qs[param][0])
            except ValueError:
                return 1
        return 1

    @staticmethod
    def _guess_offset_start(url: str, param: str) -> int:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if param in qs:
            try:
                return int(qs[param][0])
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _build_page_url(url: str, param: str, value: int) -> str:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        qs[param] = [str(value)]
        query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=query))

