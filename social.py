"""社交媒体公开内容采集。

只采集**无需登录即可访问**的公开数据，通过平台官方提供的公开接口完成：

* RSS 源（博客、播客、站点动态等任意公开订阅源）
* YouTube 频道视频列表（公开 feed）与视频元数据（oEmbed）
* bilibili UP 主公开投稿（公开 API）
* 微博用户公开主页（公开 API）
* Mastodon 公开时间线 / 账号状态
* Reddit 公开版块、用户帖子（``.json`` 公开接口）
* Telegram 公开频道预览页

不做登录态模拟、不做验证码绕过；接口返回非公开或需要鉴权时会直接报错，
由界面提示用户改用官方开放平台或申请 API 权限。
"""

import json
import re
import urllib.parse
import urllib.request

from url_guard import UnsafeURLError, validate_url
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

from bs4 import BeautifulSoup


SUPPORTED_SOURCES = (
    "rss",
    "youtube",
    "bilibili",
    "weibo",
    "mastodon",
    "reddit",
    "telegram",
)

SOURCE_LABELS = {
    "rss": "RSS / Atom 订阅源",
    "youtube": "YouTube 频道",
    "bilibili": "bilibili UP 主",
    "weibo": "微博用户",
    "mastodon": "Mastodon",
    "reddit": "Reddit",
    "telegram": "Telegram 公开频道",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class SocialError(Exception):
    """社交媒体采集异常。"""


def normalize_social_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(config or {})
    source = str(cfg.get("source") or "rss").lower()
    if source not in SUPPORTED_SOURCES:
        raise SocialError(f"不支持的平台: {source}（可选 {', '.join(SUPPORTED_SOURCES)}）")
    target = str(cfg.get("target") or "").strip()
    if not target:
        raise SocialError("请填写要采集的公开账号 / 频道 / 订阅源地址")
    try:
        limit = int(cfg.get("limit") or 20)
    except (TypeError, ValueError):
        raise SocialError("采集条数必须是整数")
    return {
        "source": source,
        "target": target,
        "limit": max(1, min(limit, 500)),
        "with_comments": bool(cfg.get("with_comments", False)),
    }


def _http_get_json(url: str, referer: str = "") -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _call_json(get_json, url: str, referer: str = "") -> Any:
    """调用 JSON 获取函数；注入实现可以不支持 referer 参数。"""
    if referer:
        try:
            return get_json(url, referer=referer)
        except TypeError:
            return get_json(url)
    return get_json(url)


def _parse_rss_datetime(value: str) -> str:
    """把 RSS/Atom 时间转成统一格式，解析失败时原样返回。"""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    try:
        from datetime import datetime

        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return value


def parse_rss(xml_text: str, limit: int = 20) -> List[Dict[str, str]]:
    """解析 RSS 2.0 / Atom / RDF 三种常见订阅格式。"""
    soup = BeautifulSoup(xml_text, "xml")
    rows: List[Dict[str, str]] = []
    for item in soup.find_all("item")[:limit]:
        link_node = item.find("link")
        link = (link_node.get_text(strip=True) if link_node else "")
        guid_node = item.find("guid")
        # RDF 里的 link 可能为空，回退到 guid
        if not link and guid_node is not None:
            link = guid_node.get_text(strip=True)
        rows.append({
            "标题": item.find("title").get_text(strip=True) if item.find("title") else "",
            "链接": link,
            "摘要": re.sub(r"<[^>]+>", "", item.find("description").get_text(" ", strip=True)) if item.find("description") else "",
            "发布时间": _parse_rss_datetime(item.find("pubDate").get_text(strip=True) if item.find("pubDate") else ""),
            "作者": item.find("author").get_text(strip=True) if item.find("author") else "",
            "平台": SOURCE_LABELS["rss"],
        })
    if rows:
        return rows
    for entry in soup.find_all("entry")[:limit]:
        link = ""
        for link_node in entry.find_all("link"):
            if link_node.get("rel", "alternate") == "alternate":
                link = link_node.get("href", "")
                break
            link = link or link_node.get("href", "")
        author = entry.find("author")
        summary = entry.find("summary") or entry.find("content")
        rows.append({
            "标题": entry.find("title").get_text(strip=True) if entry.find("title") else "",
            "链接": link,
            "摘要": re.sub(r"<[^>]+>", "", summary.get_text(" ", strip=True)) if summary else "",
            "发布时间": _parse_rss_datetime(
                (entry.find("updated") or entry.find("published")).get_text(strip=True)
                if (entry.find("updated") or entry.find("published")) else ""
            ),
            "作者": (author.find("name").get_text(strip=True) if author and author.find("name") else ""),
            "平台": SOURCE_LABELS["rss"],
        })
    return rows


def _extract_youtube_channel_id(target: str, fetch_text=None) -> str:
    get_text = fetch_text or _http_get_text
    if target.startswith("UC") and len(target) == 24:
        return target
    parsed = urllib.parse.urlparse(target if "://" in target else "https://" + target)
    path = parsed.path.strip("/")
    if path.startswith("channel/"):
        return path.split("/", 1)[1].split("/")[0]
    if path.startswith("@"):
        handle = path.split("/")[0]
        html_text = get_text(f"https://www.youtube.com/{handle}")
        match = re.search(r'"channelId":"(UC[\w-]{22})"', html_text)
        if match:
            return match.group(1)
        raise SocialError("未能从频道主页解析出频道 ID，请直接填写 UC 开头的频道 ID")
    raise SocialError("请填写 https://www.youtube.com/@handle 或 UC 开头的频道 ID")


def parse_youtube_feed(xml_text: str, limit: int = 20) -> List[Dict[str, str]]:
    soup = BeautifulSoup(xml_text, "xml")
    rows: List[Dict[str, str]] = []
    for entry in soup.find_all("entry")[:limit]:
        video_id = ""
        for link in entry.find_all("link"):
            href = link.get("href", "")
            if "/watch?v=" in href:
                video_id = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("v", [""])[0]
        stats = entry.find("media:statistics")
        rows.append({
            "标题": entry.find("title").get_text(strip=True) if entry.find("title") else "",
            "链接": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "视频ID": video_id,
            "发布时间": _parse_rss_datetime(entry.find("published").get_text(strip=True) if entry.find("published") else ""),
            "播放量": stats.get("views", "") if stats else "",
            "作者": entry.find("author").find("name").get_text(strip=True) if entry.find("author") and entry.find("author").find("name") else "",
            "平台": SOURCE_LABELS["youtube"],
        })
    return rows


def parse_bilibili_user(payload: Dict[str, Any], limit: int = 20) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    vlist = ((payload or {}).get("data") or {}).get("list") or {}
    for video in (vlist.get("vlist") or [])[:limit]:
        bvid = video.get("bvid", "")
        rows.append({
            "标题": re.sub(r"<[^>]+>", "", video.get("title", "")),
            "链接": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "视频ID": bvid,
            "发布时间": str(video.get("created", "")),
            "播放量": str(video.get("play", "")),
            "弹幕数": str(video.get("video_review", "")),
            "作者": video.get("author", ""),
            "平台": SOURCE_LABELS["bilibili"],
        })
    return rows


def parse_weibo_user(payload: Dict[str, Any], limit: int = 20) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for status in ((payload or {}).get("data") or {}).get("list", [])[:limit]:
        text = re.sub(r"<[^>]+>", "", status.get("text", ""))
        rows.append({
            "内容": text,
            "链接": f"https://m.weibo.cn/detail/{status.get('id', '')}" if status.get("id") else "",
            "发布时间": status.get("created_at", ""),
            "点赞": str(status.get("attitudes_count", "")),
            "评论": str(status.get("comments_count", "")),
            "转发": str(status.get("reposts_count", "")),
            "作者": (status.get("user") or {}).get("screen_name", ""),
            "平台": SOURCE_LABELS["weibo"],
        })
    return rows


def parse_mastodon_statuses(payload: Any, limit: int = 20) -> List[Dict[str, str]]:
    if isinstance(payload, dict) and "account" in payload:
        payload = [payload]
    rows: List[Dict[str, str]] = []
    for status in (payload or [])[:limit]:
        if not isinstance(status, dict):
            continue
        rows.append({
            "内容": re.sub(r"<[^>]+>", "", status.get("content", "")),
            "链接": status.get("url") or status.get("uri", ""),
            "发布时间": status.get("created_at", ""),
            "点赞": str(status.get("favourites_count", "")),
            "转发": str(status.get("reblogs_count", "")),
            "回复": str(status.get("replies_count", "")),
            "作者": (status.get("account") or {}).get("acct", ""),
            "平台": SOURCE_LABELS["mastodon"],
        })
    return rows


def parse_reddit_listing(payload: Dict[str, Any], limit: int = 20) -> List[Dict[str, str]]:
    children = (((payload or {}).get("data") or {}).get("children") or [])[:limit]
    rows: List[Dict[str, str]] = []
    for child in children:
        post = (child or {}).get("data") or {}
        rows.append({
            "标题": post.get("title", ""),
            "链接": "https://www.reddit.com" + post.get("permalink", "") if post.get("permalink") else post.get("url", ""),
            "外部链接": post.get("url_overridden_by_dest") or post.get("url", ""),
            "发布时间": str(post.get("created_utc", "")),
            "点赞": str(post.get("score", "")),
            "评论数": str(post.get("num_comments", "")),
            "作者": post.get("author", ""),
            "版块": post.get("subreddit", ""),
            "平台": SOURCE_LABELS["reddit"],
        })
    return rows


def parse_telegram_channel(html_text: str, limit: int = 20) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text, "lxml")
    rows: List[Dict[str, str]] = []
    title = soup.select_one(".tgme_channel_info_header_title")
    channel = title.get_text(strip=True) if title else ""
    for block in soup.select(".tgme_widget_message")[:limit]:
        text_node = block.select_one(".tgme_widget_message_text")
        time_node = block.select_one("time[datetime]")
        link = ""
        post_link = block.select_one("a.tgme_widget_message_date")
        if post_link is not None:
            link = post_link.get("href", "")
        views_node = block.select_one(".tgme_widget_message_views")
        rows.append({
            "内容": text_node.get_text(" ", strip=True) if text_node else "",
            "链接": link,
            "发布时间": time_node.get("datetime", "") if time_node else "",
            "阅读量": views_node.get_text(strip=True) if views_node else "",
            "作者": channel,
            "平台": SOURCE_LABELS["telegram"],
        })
    return rows


def fetch_social_rows(config: Dict[str, Any], fetch=None, fetch_json=None) -> List[Dict[str, str]]:
    """按平台拉取公开数据，返回统一结构的行。

    ``fetch`` / ``fetch_json`` 可由调用方注入（例如复用主爬虫的代理、重试与
    robots 策略）；不注入时使用内置的公开接口直连实现。
    """
    get_text = fetch or _http_get_text
    get_json = fetch_json or _http_get_json
    cfg = normalize_social_config(config)
    source, target, limit = cfg["source"], cfg["target"], cfg["limit"]
    if source == "rss":
        return parse_rss(get_text(target), limit)
    if source == "youtube":
        channel_id = _extract_youtube_channel_id(target, get_text)
        return parse_youtube_feed(
            get_text(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"), limit
        )
    if source == "bilibili":
        uid = target
        if not uid.isdigit():
            match = re.search(r"space\.bilibili\.com/(\d+)", target)
            if not match:
                raise SocialError("请填写 bilibili 数字 UID 或 space.bilibili.com/<UID> 链接")
            uid = match.group(1)
        payload = _call_json(
            get_json,
            f"https://api.bilibili.com/x/space/arc/search?mid={uid}&ps={min(limit, 50)}&pn=1",
            referer=f"https://space.bilibili.com/{uid}",
        )
        if payload.get("code") not in (0, None):
            raise SocialError(f"bilibili 接口返回错误: {payload.get('message') or payload.get('code')}")
        return parse_bilibili_user(payload, limit)
    if source == "weibo":
        uid = target
        if not uid.isdigit():
            match = re.search(r"weibo\.com/(?:u/)?(\d+)", target)
            if not match:
                raise SocialError("请填写微博数字 UID 或 https://weibo.com/u/<UID> 链接")
            uid = match.group(1)
        payload = _call_json(
            get_json,
            f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}",
            referer=f"https://m.weibo.cn/u/{uid}",
        )
        return parse_weibo_user(payload, limit)
    if source == "mastodon":
        if "/@" in target:
            base, _, account = target.replace("https://", "").replace("http://", "").partition("/")
            lookup_url = f"https://{base}/api/v1/accounts/lookup?acct={urllib.parse.quote(account.lstrip('@'))}"
            # 实例域名由用户输入，必须校验，防止指向内网地址（SSRF）。
            try:
                validate_url(lookup_url)
            except UnsafeURLError:
                raise SocialError("Mastodon 实例地址指向受保护网络，已阻止")
            payload = get_json(lookup_url)
            if not payload.get("id"):
                raise SocialError("Mastodon 账号不存在或未公开")
            payload = get_json(
                f"https://{base}/api/v1/accounts/{payload['id']}/statuses?limit={min(limit, 40)}&exclude_replies=true"
            )
            return parse_mastodon_statuses(payload, limit)
        public_url = f"{target.rstrip('/')}/api/v1/timelines/public?limit={min(limit, 40)}"
        try:
            validate_url(public_url)
        except UnsafeURLError:
            raise SocialError("Mastodon 实例地址指向受保护网络，已阻止")
        payload = get_json(public_url)
        return parse_mastodon_statuses(payload, limit)
    if source == "reddit":
        path = target
        if target.startswith("http"):
            parsed = urllib.parse.urlparse(target)
            path = parsed.path
        path = path.strip("/")
        if not path:
            raise SocialError("请填写版块名（如 python）或 reddit 用户/链接")
        if path.startswith("user/") or path.startswith("u/"):
            url = f"https://www.reddit.com/{path}/submitted.json?limit={min(limit, 100)}"
        elif path.startswith("r/"):
            url = f"https://www.reddit.com/{path}.json?limit={min(limit, 100)}"
        else:
            url = f"https://www.reddit.com/r/{path}.json?limit={min(limit, 100)}"
        return parse_reddit_listing(get_json(url), limit)
    if source == "telegram":
        channel = target
        if target.startswith("http"):
            channel = urllib.parse.urlparse(target).path.strip("/").split("/")[0]
        channel = channel.lstrip("@")
        if not channel:
            raise SocialError("请填写公开频道用户名，如 @durov 或 https://t.me/durov")
        return parse_telegram_channel(get_text(f"https://t.me/s/{channel}"), limit)
    raise SocialError(f"不支持的平台: {source}")
