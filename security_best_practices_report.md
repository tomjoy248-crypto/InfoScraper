# InfoScraper 安全扫描报告

扫描范围：`sl_repo/SL-crawler` 全部 Python 源码（37 个 `.py` 文件）。
扫描日期：2026-11-07

> **修复状态**：截至 **v4.17.2**（2026-11-07），本报告全部发现已修复并发布：
> - M-1：v4.17.1（`url_guard.py` 统一校验，probe_http 接入）；重定向残余 v4.17.2（`_ValidatingRedirectHandler`）
> - M-2：v4.17.2（api_config.headers/body 整体 DPAPI 加密）
> - M-3：v4.17.1（Mastodon 请求前校验实例地址）
> - L-1：v4.17.2（非 Windows 改用 Fernet 加密，密钥 0600 文件）
> 已知残余：`url_guard` 校验 DNS 与实际连接存在理论 TOCTOU（DNS rebinding）窗口，风险较低，暂不处理。

## 执行摘要

整体安全水位**良好**。核心采集链路（`scraper.py`）有扎实的 SSRF 防护，SQL 全部参数化，文件导出有 CSV 注入防护与敏感字段脱敏，配置文件有路径穿越防护与 DPAPI 加密。

发现 **3 个中危** 与 **1 个低危** 问题，集中在两处：
1. `recon_core.py` / `social.py` 的部分请求绕过了 `scraper.py` 的私有 IP 校验，存在 SSRF 缺口；
2. API 凭证（`api_config.headers` / `api_config.body`）在任务配置中**明文存储**，与 Cookie/代理的加密待遇不一致。

未发现：硬编码密钥、`shell=True`、`eval`/`exec`、`pickle`/`yaml.load`/`marshal` 反序列化、`verify=False`、SQL 注入、路径穿越。

---

## 中危（Medium）

### M-1　`recon_core.probe_http` 缺少私有 IP 校验，且默认跟随重定向 — SSRF

**状态**：✅ 已修复（v4.17.1 + v4.17.2 重定向部分）

**文件**：`recon_core.py` 第 187-249 行

```python
def probe_http(asset: Asset, timeout: int = 8, delay: float = 0.2) -> Asset:
    for scheme in ("https", "http"):
        url = f"{scheme}://{asset.value}/"
        request = urllib.request.Request(url, ...)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            ...
            asset.final_url = response.geturl()   # urllib 默认跟随重定向
```

**影响**：`asset.value` 来自子域名枚举结果（crt.sh / hackertarget）或用户手动输入。若某公开子域名解析到内网 IP（split-horizon DNS），或目标返回 `302` 跳转到 `http://169.254.169.254/`（云元数据）等内网地址，`urllib` 会**直接请求内网**，造成 SSRF。

与 `scraper.py._validate_url`（第 251-271 行）形成明显不一致：后者会拦截私有/回环/链路本地/保留地址并做 DNS 重绑定锁定，而 `probe_http` 完全没有这层防护。

**建议**：抽取 `scraper._validate_url` 的校验逻辑为可复用函数（或在 `recon_core` 中实现等价校验），在 `probe_http` 请求前调用；同时设置 `urllib.request.Request` 不跟随重定向，或对 `response.geturl()` 再次校验。

---

### M-2　API 凭证在任务配置中明文存储

**状态**：✅ 已修复（v4.17.2，`config.py` API_SENSITIVE_SUBKEYS + `_decrypt_tree`）

**文件**：`config.py` 第 13 行；`gui.py` 第 1473-1477 行

```python
SENSITIVE_KEYS = ("cookie", "proxy", "proxy_single")
...
"api_config": {
    "headers": api_headers,   # 可含 Authorization / X-API-Key / Cookie
    "body": api_body,         # 可含 token / secret
    ...
}
```

`save_task` 只对 `SENSITIVE_KEYS` 中的字段调用 `secure_storage.encrypt`（DPAPI）。`api_config.headers` 和 `api_config.body` 虽然可能包含 `Authorization: Bearer <token>`、`X-API-Key`、`Cookie` 等敏感凭证，却以**明文 JSON** 写入 `tasks/<name>.json`。

**影响**：任何能读取该目录的人（同机其他用户、恶意软件、备份泄露）都能直接拿到 API 凭证。Cookie 已加密，待遇不对等。

**建议**：将 `api_headers`、`api_body`（或至少其中值匹配敏感模式的条目）纳入加密范围。可在 `protect()` 中对 `api_config.headers` / `api_config.body` 的字符串值调用 `secure_storage.encrypt`，加载时对应解密。注意 `load_task` 当前只解密顶层 `SENSITIVE_KEYS`，需同步扩展到 `api_config` 嵌套结构。

---

### M-3　`social.py` Mastodon 实例主机未校验私有 IP — SSRF

**状态**：✅ 已修复（v4.17.1，`url_guard.validate_url` 接入 Mastodon 分支）

**文件**：`social.py` 第 350-357 行

```python
base, _, account = target.replace("https://", "").replace("http://", "").partition("/")
...
f"https://{base}/api/v1/accounts/lookup?acct={urllib.parse.quote(account.lstrip('@'))}"
```

`base` 完全来自用户输入的 Mastodon 实例地址，未做私有 IP 校验即直接请求。若用户输入 `127.0.0.1` 或内网主机名，会发起内网请求。

**影响**：与 M-1 同类，SSRF 缺口。其余社媒源（YouTube/B站/微博/Reddit/Telegram）的主机是硬编码的，风险较低。

**建议**：复用 M-1 中抽取的 URL/主机校验函数，对 `base` 做同样的私有 IP 拦截。

---

## 低危（Low）

### L-1　非 Windows 平台敏感数据仅 base64 编码

**状态**：✅ 已修复（v4.17.2，`cryptography` Fernet + 0600 密钥文件；`database.init_db` 同步识别 `fernet:` 前缀）

**文件**：`secure_storage.py` 第 23-25 行

```python
if not _IS_WINDOWS:
    logger.warning("非 Windows 平台，敏感数据仅做 base64 编码，未加密")
    return "b64:" + base64.b64encode(raw).decode("ascii")
```

**影响**：在非 Windows 平台（CI 的 Ubuntu runner、或未来的 macOS/Linux 移植）上，Cookie/代理等敏感字段只是 base64，等同明文。已通过日志警告说明，且项目当前目标平台为 Windows，风险较低。

**建议**：保持现状可接受；若计划跨平台发布，应改用 `keyring` 或平台原生密钥库。

---

## 已确认的安全实践（正面）

| 机制 | 位置 | 说明 |
|---|---|---|
| SSRF 防护（核心链路） | `scraper.py:251` | 限 http/https、拦截私有/回环/链路本地/保留 IP、DNS 重绑定锁定、`trusted_hosts` 白名单 |
| 禁止自动重定向 | `scraper.py:204,207,232` | `allow_redirects=False`，防止重定向 SSRF |
| SQL 参数化 | `database.py` 全部 | 所有查询用 `?` 占位符；`existing_keys` 的 f-string 仅拼接固定模板，用户输入走参数绑定 |
| 路径穿越防护 | `config.py:17-18,50-53` | 任务名禁止 `..` 与路径分隔符，文件名严格白名单 |
| 凭证加密 | `config.py:63-68` + `secure_storage.py` | Cookie/代理用 DPAPI 加密（Windows） |
| 原子写入 | `config.py:72-78` | `tempfile` + `fsync` + `os.replace`，防崩溃损坏 |
| CSV 注入防护 | `exporter.py:8-13` | 单元格以 `= + - @ \t \r` 开头时前缀 `'` |
| 导出脱敏 | `exporter.py:24,32,44` + `redact.py` | 导出前对 cookie/token/api_key/password 等字段脱敏 |
| 无危险模式 | 全仓 | 无 `shell=True`、`eval`/`exec`、`pickle`/`yaml.load`/`marshal`、`verify=False` |
| robots.txt 尊重 | `scraper.py:182-187` | 可配置 `respect_robots`，限流/403 时 fail-closed 可选 |

---

## 修复优先级建议

1. ~~**M-1 + M-3**（SSRF 防护统一）~~：已完成。
2. ~~**M-2**（API 凭证加密）~~：已完成。
3. ~~**L-1**（跨平台加密）~~：已完成。

后续可选跟进：`url_guard` 的 DNS rebinding TOCTOU（需锁定解析 IP 建连）。
