import json
import socket
import threading
import time
import urllib.parse
import urllib.request
import re
import uuid
from typing import Callable, List, Optional, Set


DEFAULT_WORDLIST = [
    "www", "mail", "ftp", "localhost", "blog", "shop", "forum", "news",
    "m", "mobile", "api", "dev", "test", "staging", "admin", "portal",
    "webmail", "webdisk", "cpanel", "whm", "ns1", "ns2", "dns", "smtp",
    "pop", "imap", "vpn", "remote", "git", "svn", "cdn", "static",
    "assets", "img", "images", "css", "js", "app", "apps", "panel",
    "manage", "backend", "frontend", "service", "services", "support",
    "help", "docs", "wiki", "kb", "status", "monitor", "grafana",
    "prometheus", "kibana", "elastic", "search", "db", "database",
    "redis", "mongo", "mysql", "postgres", "kafka", "rabbitmq",
    "jenkins", "gitlab", "github", "bitbucket", "confluence", "jira",
    "owa", "autodiscover", "lyncdiscover", "sip", "xmpp", "meet",
    "teams", "slack", "zoom", "webex", "drive", "cloud", "storage",
    "backup", "archive", "old", "new", "beta", "alpha", "demo",
    "trial", "sandbox", "preview", "release", "prod", "production",
    "uat", "qa", "sec", "security", "ops", "sysadmin", "noc",
    "log", "logs", "trace", "metrics", "alert", "alerts",
    "ca", "crl", "ocsp", "pki", "cert", "certs", "ssl",
    "payment", "pay", "billing", "invoice", "order", "orders",
    "cart", "checkout", "account", "user", "users", "member",
    "members", "profile", "dashboard", "home", "start", "login",
    "auth", "sso", "oauth", "id", "identity", "register", "signup",
    "join", "invite", "partner", "partners", "client", "clients",
    "customer", "customers", "vendor", "vendors", "supplier",
    "api-v1", "api-v2", "api-v3", "rest", "graphql", "swagger",
    "openapi", "ws", "wss", "socket", "sockets", "rtmp", "hls",
    "webrtc", "turn", "stun", "voip", "pbx", "sip",
    "cn", "hk", "us", "eu", "asia", "global", "intl",
    "east", "west", "north", "south", "bj", "sh", "sz", "gz",
]


def dns_resolve(subdomain: str, timeout: float = 2.0) -> Optional[str]:
    """尝试解析子域名，成功返回 IP，失败返回 None。"""
    try:
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(subdomain)
        return ip
    except socket.error:
        return None
    finally:
        socket.setdefaulttimeout(None)


def brute_subdomains(
    domain: str,
    wordlist: Optional[List[str]] = None,
    threads: int = 50,
    timeout: float = 2.0,
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> List[dict]:
    """使用字典爆破收集子域名。"""
    words = wordlist or DEFAULT_WORDLIST
    # Detect wildcard DNS before brute force to avoid reporting every word.
    wildcard = dns_resolve(f"{uuid.uuid4().hex}.{domain}", timeout)
    if wildcard:
        if on_log: on_log("检测到泛解析，跳过 DNS 字典爆破以避免误报")
        return []
    threads = max(1, min(int(threads), 100))
    found: Set[str] = set()
    results: List[dict] = []
    total = len(words)
    lock = threading.Lock()
    counter = [0]

    def check(word: str):
        subdomain = f"{word}.{domain}"
        ip = dns_resolve(subdomain, timeout)
        with lock:
            counter[0] += 1
            if on_progress:
                on_progress(counter[0], total)
        if ip:
            with lock:
                if subdomain not in found:
                    found.add(subdomain)
                    results.append({"子域名": subdomain, "IP": ip, "来源": "DNS爆破"})
                    if on_log:
                        on_log(f"发现子域名: {subdomain} -> {ip}")

    pool = []
    for word in words:
        while len(pool) >= threads:
            for t in pool[:]:
                if not t.is_alive():
                    pool.remove(t)
            time.sleep(0.01)
        t = threading.Thread(target=check, args=(word,), daemon=True)
        t.start()
        pool.append(t)

    for t in pool:
        t.join()
    return results


def fetch_crtsh(domain: str, on_log: Optional[Callable[[str], None]] = None) -> List[dict]:
    """通过 crt.sh 证书透明度查询子域名。"""
    url = f"https://crt.sh/?q=%.{urllib.parse.quote(domain)}&output=json"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        if on_log:
            on_log(f"crt.sh 查询失败: {e}")
        return []

    found: Set[str] = set()
    results: List[dict] = []
    for entry in data:
        name = entry.get("name_value", "").strip().lower()
        if not name:
            continue
        # 可能包含多行
        for sub in name.split("\n"):
            sub = sub.strip()
            if not sub or sub.startswith("*."):
                continue
            if sub.endswith(f".{domain}") and sub not in found:
                found.add(sub)
                results.append({"子域名": sub, "IP": "", "来源": "crt.sh"})
                if on_log:
                    on_log(f"crt.sh 发现: {sub}")
    return results


def collect_subdomains(
    domain: str,
    enable_brute: bool = True,
    enable_crtsh: bool = True,
    wordlist: Optional[List[str]] = None,
    threads: int = 50,
    timeout: float = 2.0,
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> List[dict]:
    """综合收集子域名。"""
    domain = domain.strip().lower().rstrip(".")
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        raise ValueError("域名格式无效，请输入类似 example.com 的根域名")
    all_results: List[dict] = []
    seen: Set[str] = set()

    if enable_crtsh:
        if on_log:
            on_log("开始 crt.sh 证书透明度查询...")
        for r in fetch_crtsh(domain, on_log):
            if r["子域名"] not in seen:
                seen.add(r["子域名"])
                all_results.append(r)

    if enable_brute:
        if on_log:
            on_log("开始 DNS 字典爆破...")
        for r in brute_subdomains(domain, wordlist, threads, timeout, on_progress, on_log):
            if r["子域名"] not in seen:
                seen.add(r["子域名"])
                # 如果 crt.sh 已发现，补充 IP
                all_results.append(r)
            else:
                # 补充 IP
                for item in all_results:
                    if item["子域名"] == r["子域名"] and not item["IP"]:
                        item["IP"] = r["IP"]
                        item["来源"] = "crt.sh + DNS爆破"

    return all_results
