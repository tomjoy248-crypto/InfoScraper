import pytest

from social import (
    SUPPORTED_SOURCES,
    SocialError,
    _call_json,
    _extract_youtube_channel_id,
    _parse_rss_datetime,
    fetch_social_rows,
    normalize_social_config,
    parse_bilibili_user,
    parse_mastodon_statuses,
    parse_reddit_listing,
    parse_rss,
    parse_telegram_channel,
    parse_weibo_user,
    parse_youtube_feed,
)

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>第一篇</title>
    <link>https://example.com/1</link>
    <description>&lt;p&gt;摘要一&lt;/p&gt;</description>
    <pubDate>Mon, 04 Nov 2024 10:00:00 GMT</pubDate>
    <author>alice</author>
  </item>
  <item>
    <title>第二篇</title>
    <guid>https://example.com/2</guid>
    <description>摘要二</description>
  </item>
</channel></rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>原子条目</title>
    <link rel="alternate" href="https://example.org/a"/>
    <updated>2024-11-04T10:00:00Z</updated>
    <summary>原子摘要</summary>
    <author><name>bob</name></author>
  </entry>
</feed>
"""

YOUTUBE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry>
    <title>视频标题</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
    <published>2024-11-04T10:00:00Z</published>
    <author><name>某频道</name></author>
    <media:statistics views="1234"/>
  </entry>
</feed>
"""

TELEGRAM_HTML = """
<html><body>
  <div class="tgme_channel_info_header_title">某公开频道</div>
  <div class="tgme_widget_message">
    <div class="tgme_widget_message_text">频道消息内容</div>
    <time datetime="2024-11-04T10:00:00+00:00"></time>
    <a class="tgme_widget_message_date" href="https://t.me/chan/1"></a>
    <span class="tgme_widget_message_views">2.1K</span>
  </div>
</body></html>
"""


def test_normalize_social_config_accepts_all_sources():
    for source in SUPPORTED_SOURCES:
        cfg = normalize_social_config({"source": source, "target": "x", "limit": 5})
        assert cfg["source"] == source
        assert cfg["limit"] == 5


@pytest.mark.parametrize("config", [
    {"source": "douyin", "target": "x"},
    {"source": "rss", "target": "   "},
    {"source": "rss", "target": "x", "limit": "abc"},
])
def test_normalize_social_config_rejects_bad_values(config):
    with pytest.raises(SocialError):
        normalize_social_config(config)


def test_normalize_social_config_clamps_limit():
    assert normalize_social_config({"source": "rss", "target": "x", "limit": 99999})["limit"] == 500
    # 0 是假值，会走 `or 20` 的默认分支
    assert normalize_social_config({"source": "rss", "target": "x", "limit": 0})["limit"] == 20


def test_parse_rss_handles_rss_and_guid_fallback():
    rows = parse_rss(RSS_XML)
    assert [r["标题"] for r in rows] == ["第一篇", "第二篇"]
    assert rows[0]["链接"] == "https://example.com/1"
    assert rows[0]["摘要"] == "摘要一"
    assert rows[1]["链接"] == "https://example.com/2"
    assert rows[0]["作者"] == "alice"
    assert rows[0]["平台"] == "RSS / Atom 订阅源"


def test_parse_rss_handles_atom_feed():
    rows = parse_rss(ATOM_XML)
    assert len(rows) == 1
    assert rows[0]["链接"] == "https://example.org/a"
    assert rows[0]["摘要"] == "原子摘要"
    assert rows[0]["作者"] == "bob"


def test_parse_rss_respects_limit():
    assert len(parse_rss(RSS_XML, limit=1)) == 1


def test_parse_rss_datetime_formats_known_values():
    assert _parse_rss_datetime("Mon, 04 Nov 2024 10:00:00 GMT")
    assert _parse_rss_datetime("2024-11-04T10:00:00Z")
    assert _parse_rss_datetime("不是时间") == "不是时间"
    assert _parse_rss_datetime("") == ""


def test_parse_youtube_feed_extracts_video_id_and_views():
    rows = parse_youtube_feed(YOUTUBE_XML)
    assert rows[0]["视频ID"] == "abc123"
    assert rows[0]["链接"] == "https://www.youtube.com/watch?v=abc123"
    assert rows[0]["播放量"] == "1234"
    assert rows[0]["作者"] == "某频道"


def test_extract_youtube_channel_id_from_forms():
    channel_id = "UC" + "a" * 22
    assert _extract_youtube_channel_id(channel_id) == channel_id
    assert _extract_youtube_channel_id(f"https://www.youtube.com/channel/{channel_id}") == channel_id
    handle_id = "UC" + "b" * 22
    got = _extract_youtube_channel_id(
        "https://www.youtube.com/@demo",
        lambda url: f'<html><script>"channelId":"{handle_id}"</script></html>',
    )
    assert got == handle_id


@pytest.mark.parametrize("target", ["https://www.youtube.com/foo", "demo"])
def test_extract_youtube_channel_id_rejects_unknown_forms(target):
    with pytest.raises(SocialError):
        _extract_youtube_channel_id(target)


def test_parse_bilibili_payload():
    payload = {"code": 0, "data": {"list": {"vlist": [
        {"bvid": "BV1xx", "title": "<em>标题</em>", "created": 1700000000, "play": 10,
         "video_review": 2, "author": "UP"}
    ]}}}
    rows = parse_bilibili_user(payload)
    assert rows[0]["标题"] == "标题"
    assert rows[0]["链接"] == "https://www.bilibili.com/video/BV1xx"
    assert rows[0]["平台"] == "bilibili UP 主"


def test_parse_weibo_payload_strips_tags():
    payload = {"data": {"list": [
        {"text": "<a>话题</a>正文", "id": 42, "created_at": "刚刚",
         "attitudes_count": 3, "comments_count": 4, "reposts_count": 5,
         "user": {"screen_name": "小明"}}
    ]}}
    rows = parse_weibo_user(payload)
    assert rows[0]["内容"] == "话题正文"
    assert rows[0]["链接"] == "https://m.weibo.cn/detail/42"
    assert rows[0]["作者"] == "小明"


def test_parse_mastodon_accepts_single_status():
    status = {"content": "<p>嘟文</p>", "url": "https://m.social/@a/1", "created_at": "2024-01-01",
              "favourites_count": 1, "reblogs_count": 2, "replies_count": 3,
              "account": {"acct": "a"}}
    rows = parse_mastodon_statuses(status)
    assert len(rows) == 1
    assert rows[0]["内容"] == "嘟文"
    assert rows[0]["作者"] == "a"


def test_parse_reddit_listing_builds_permalink():
    payload = {"data": {"children": [{"data": {
        "title": "帖子", "permalink": "/r/python/comments/x/y/", "subreddit": "python",
        "score": 7, "num_comments": 2, "author": "u", "created_utc": 1700000000,
    }}]}}
    rows = parse_reddit_listing(payload)
    assert rows[0]["链接"] == "https://www.reddit.com/r/python/comments/x/y/"
    assert rows[0]["版块"] == "python"


def test_parse_telegram_channel_html():
    rows = parse_telegram_channel(TELEGRAM_HTML)
    assert rows[0]["内容"] == "频道消息内容"
    assert rows[0]["链接"] == "https://t.me/chan/1"
    assert rows[0]["阅读量"] == "2.1K"
    assert rows[0]["作者"] == "某公开频道"


def test_fetch_social_rows_rss_uses_injected_fetch():
    requested = []

    def fetch(url):
        requested.append(url)
        return RSS_XML

    rows = fetch_social_rows({"source": "rss", "target": "https://example.com/feed", "limit": 2}, fetch=fetch)
    assert len(rows) == 2
    assert requested == ["https://example.com/feed"]


def test_fetch_social_rows_reddit_uses_injected_json():
    seen = []

    def fetch_json(url):
        seen.append(url)
        return {"data": {"children": []}}

    rows = fetch_social_rows({"source": "reddit", "target": "python"}, fetch_json=fetch_json)
    assert rows == []
    assert seen == ["https://www.reddit.com/r/python.json?limit=20"]


def test_fetch_social_rows_bilibili_passes_referer_through_injection():
    calls = []

    def fetch_json(url, referer=""):
        calls.append((url, referer))
        return {"code": 0, "data": {"list": {"vlist": []}}}

    fetch_social_rows({"source": "bilibili", "target": "123"}, fetch_json=fetch_json)
    assert calls[0][1] == "https://space.bilibili.com/123"


def test_fetch_social_rows_bilibili_rejects_bad_api_code():
    with pytest.raises(SocialError):
        fetch_social_rows(
            {"source": "bilibili", "target": "123"},
            fetch_json=lambda url, referer="": {"code": -404, "message": "不存在"},
        )


def test_fetch_social_rows_rejects_bad_uid():
    with pytest.raises(SocialError):
        fetch_social_rows({"source": "weibo", "target": "不是UID"}, fetch_json=lambda url: {})


def test_call_json_falls_back_when_referer_unsupported():
    assert _call_json(lambda url: "plain", "u", referer="r") == "plain"
    assert _call_json(lambda url, referer="": f"{url}|{referer}", "u", referer="r") == "u|r"
    assert _call_json(lambda url: "no-referer", "u") == "no-referer"
