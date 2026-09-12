import random
import re
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag
from lxml import html as lh


USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class ScraperError(Exception):
    """爬虫运行异常"""
    pass


class WebScraper:
    """通用网页爬虫：支持静态请求、CSS/XPath 解析、翻页、API 请求、反爬策略。"""

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

    def _fetch(self, url: str, method: str = "GET", payload: Optional[Dict] = None) -> str:
        if self.render:
            return self._fetch_render(url)
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                proxies = self._pick_proxy()
                if method.upper() == "POST":
                    resp = self.session.post(
                        url, data=payload, proxies=proxies, timeout=self.timeout
                    )
                else:
                    resp = self.session.get(url, proxies=proxies, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                last_error = e
                if self.random_ua:
                    self._update_headers()
                if attempt < self.retries:
                    time.sleep(random.uniform(1, 3))
        raise ScraperError(f"请求失败（重试 {self.retries} 次）: {last_error}")

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
        self._playwright_page.goto(url, wait_until="networkidle")
        return self._playwright_page.content()

    def close(self):
        if self._playwright_page:
            self._playwright_page.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._playwright_page = None
        self._browser = None
        self._pw = None

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
                    sel = field["selector"]
                    attr = field.get("attr")
                    sub = item.select_one(sel)
                    row[name] = self._extract_field(sub, attr) if sub else ""
                results.append(row)
        else:  # xpath
            tree = lh.fromstring(html_text)
            items = tree.xpath(list_selector)
            for item in items:
                row = {}
                for field in fields:
                    name = field["name"]
                    sel = field["selector"]
                    attr = field.get("attr")
                    subs = item.xpath(sel)
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
        all_results: List[Dict[str, str]] = []
        current_url = self.start_url
        page_param_start = self._guess_page_param_start(current_url, next_page_param)

        for page in range(1, max_pages + 1):
            if on_log:
                on_log(f"正在采集第 {page} 页: {current_url}")
            html_text = self._fetch(current_url)
            rows = self.parse_fields(html_text, list_selector, fields, selector_type)
            all_results.extend(rows)
            if on_progress:
                on_progress(page, len(all_results))
            if page >= max_pages:
                break

            # 下一页
            if next_page_mode == "param":
                current_url = self._build_page_url(current_url, next_page_param, page_param_start + page * next_page_step)
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
            time.sleep(sleep_time)
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
    def _build_page_url(url: str, param: str, value: int) -> str:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        qs[param] = [str(value)]
        query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=query))
