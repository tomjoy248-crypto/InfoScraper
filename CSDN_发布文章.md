# InfoScraper：面向授权目标的一站式资产信息收集工具

> GitHub 项目地址：[https://github.com/tomjoy248-crypto/InfoScraper](https://github.com/tomjoy248-crypto/InfoScraper)
>
> 最新 Windows 安装包：[Releases 下载页](https://github.com/tomjoy248-crypto/InfoScraper/releases/latest)

## 项目介绍

InfoScraper 是一个 Windows 桌面端信息收集与网页资产分析工具。它的目标是降低资产梳理的门槛：输入一个 URL、域名或 IP，即可在授权范围内收集页面资源、公开子域名、DNS、基础网络信息、技术指纹和公开接口线索，并支持导出和报告生成。

项目重点是**被动收集、低影响探测和结果留存**，适用于自有系统巡检、授权渗透测试前的资产梳理，以及公开网站的基础信息归档。

## 主要能力

### 1. URL 页面资产收集

- 自动抓取页面标题、描述、链接、图片、脚本、样式表、视频和 iframe。
- 支持限定同主机、限定页数和深度的页面爬取。
- 未配置 CSS/XPath 选择器时，可自动切换到页面资产收集模式。
- 支持 robots.txt 规则处理、重试、延迟、Cookie、代理和断点续跑。

### 2. 域名与子域名信息收集

- 使用 crt.sh 和 Hackertarget 进行公开子域名收集。
- 支持根域名、带路径 URL、带端口 URL 和 IPv4 输入。
- 收集 DNS A、AAAA、CNAME、MX、NS、TXT 记录。
- 从 robots.txt 和 sitemap.xml 中提取公开 URL。

### 3. IP、ASN 与 RDAP 信息

- DNS/IP 解析。
- ASN、组织、国家、城市等基础网络信息。
- CDN 基础判断。
- RDAP 注册组织、注册/到期/变更时间、名称服务器信息。
- C 段以保守的 `/24` 归类展示，仅用于资产关联参考。

### 4. 技术指纹与公开接口线索

- 基础识别 Nginx、Apache、IIS、Caddy、LiteSpeed、PHP、ASP.NET、Express、Gunicorn 等服务组件。
- 基础识别 WordPress、Laravel、Django、Vue、React、Next.js、Nuxt、Angular、Shopify、Drupal 等技术栈。
- 提取页面、外部 JavaScript 和 Source Map 中的公开 API 线索。
- Playwright 渲染模式下，可记录页面运行时发出的同源 API、GraphQL、REST、JSON/XML 请求。

### 5. 授权端口检查

- 仅对用户明确填写到“授权域名白名单”的主机执行。
- 使用固定常见端口集合进行低影响 TCP 连通性检查。
- 连接成功后最多读取少量服务提示，不发送攻击载荷。
- 支持取消，单个端口失败不影响其他端口结果。

### 6. 外部数据源（可选）

可在“API 配置”中保存自己的 API Key。未配置 Key 时不会影响基础功能。

- Shodan：主机信息。
- VirusTotal：域名信息。
- SecurityTrails：子域名信息。
- FOFA：域名查询，需要 API Key 和 FOFA 邮箱。

这些查询为只读调用，结果会合并进入一键流程、历史记录和导出文件。请遵守对应平台的服务条款、额度和目标授权要求。

### 7. 任务、结果与报告

- 一键全流程：子域名、DNS、HTTP、RDAP、公开 URL、可选 Provider 和授权端口检查。
- 并发资产探测与 Provider 查询。
- 运行中可取消当前任务。
- 结果保存到历史记录，支持 Excel、CSV、JSON 导出。
- 支持 HTML 报告和 PDF 报告。
- 报告包含总记录数、资产类型统计和失败/不可达目标摘要。

## 使用步骤

1. 从 Releases 下载并安装 `InfoScraper-Setup.exe`。
2. 启动程序，在“起始 URL”输入目标，例如 `https://example.com`。
3. 根据需求选择：
   - 点击“扫描页面资产”：收集网页、脚本、图片、链接和接口线索。
   - 点击“收集域名资产”：收集子域名、DNS、IP/RDAP 等信息。
   - 点击“一键全流程”：执行综合资产收集。
4. 如需分析 JavaScript 动态页面，勾选“使用 Playwright 渲染”。
5. 如需端口检查，先在“授权域名白名单”填写已获授权的主机，再点击“授权端口探测”。
6. 任务结束后，可在结果预览和历史记录中查看数据，并导出 Excel/CSV/JSON 或生成报告。

## 授权与使用说明

本工具用于自有资产、明确书面授权的测试目标或合法公开资料的整理。

- 不应用于未授权扫描。
- 端口检查需要用户显式填写授权白名单。
- 工具不包含密码爆破、认证绕过、漏洞利用、持久化、横向移动或数据窃取功能。
- 外部 API 的使用需要用户自行配置合法 Key，并遵守供应商规则。

## 当前限制

- 子域名结果依赖公开数据源，无法保证覆盖全部资产。
- 指纹规则是持续扩展的规则集，不等同于完整商业 Wappalyzer 数据库。
- JavaScript 分析主要覆盖静态线索和可见运行时请求；复杂混淆、登录后请求和深层 Source Map 仍可能遗漏。
- PDF 报告需要本机安装 Playwright Chromium。
- 不同网络环境可能导致公开数据源超时或限流，工具会保留可用结果并记录失败信息。

## 获取项目

- GitHub：<https://github.com/tomjoy248-crypto/InfoScraper>
- Releases：<https://github.com/tomjoy248-crypto/InfoScraper/releases/latest>

欢迎提交 Issue 和改进建议。使用前请确认目标授权范围。
