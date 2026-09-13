# 通用信息收集爬虫

一个基于 Python + tkinter 的桌面爬虫工具，支持公开网页、API、搜索引擎结果、社交媒体公开内容等数据采集。

## 功能特性

- 可视化配置采集任务
- 支持 CSS 选择器 / XPath 解析
- 支持 URL 翻页和参数翻页
- 支持 Cookie 和自定义 User-Agent
- 支持导出 CSV / Excel / JSON
- 支持保存/加载采集任务
- **SQLite 数据库持久化历史记录**
- **应用内定时任务**
- **反爬策略**：随机 UA、代理池、失败重试、随机延迟、Playwright 动态渲染
- **可视化选择器助手**：打开浏览器，点击元素自动生成选择器
- **数据处理**：字段级清洗规则（去空格、去 HTML、提取数字/手机/邮箱等）
- **数据去重**：按指定字段或整行去重
- **任务模板**：内置人物信息、商品信息、新闻列表模板
- **统计面板**：显示原始数量、去重后数量、采集耗时
- **子域名收集**：DNS 字典爆破 + crt.sh 证书透明度查询

## 快速下载（Windows 安装包）

不需要安装 Python，下载安装包后双击运行即可：

- [InfoScraper-Setup.exe 下载](https://github.com/tomjoy248-crypto/SL-crawler-/releases/download/v1.1.0/InfoScraper-Setup.exe)

下载后双击安装，安装完成后会在开始菜单和桌面（可选）创建快捷方式。

## 源码运行

### 安装依赖

```bash
cd info_scraper
pip install -r requirements.txt
```

如需抓取 JS 渲染页面或使用可视化选择器，额外安装浏览器：

```bash
playwright install chromium
```

## 启动

```bash
python main.py
```

## 界面标签页

1. **采集配置**：URL、选择器、翻页、字段、结果预览
2. **反爬与代理**：随机 UA、渲染、重试、延迟、代理池
3. **数据处理**：去重配置、字段清洗规则
4. **定时任务**：按分钟间隔自动执行当前任务
5. **子域名收集**：DNS 爆破、crt.sh 证书查询、导出结果
6. **历史记录**：SQLite 自动保存，可查看/导出/删除

## 使用流程

1. 在「采集配置」页填写目标 URL、列表选择器和字段选择器
2. （可选）点击「可视化选元素」打开浏览器点选生成选择器
3. （可选）从顶部模板下拉框选择「人物信息」或「商品信息」模板
4. 在「数据处理」页配置去重字段和清洗规则
5. 在「反爬与代理」页配置随机 UA、代理池、延迟等
6. 点击「开始采集」，结果会自动保存到「历史记录」
7. 在历史记录页查看详情或导出 Excel/CSV/JSON

## 定时任务

在「定时任务」页设置间隔分钟数，点击「添加当前任务为定时任务」。程序会在后台按间隔自动执行采集并保存结果。

## 项目结构

```
info_scraper/
├── main.py           # 程序入口
├── gui.py            # 桌面界面（含标签页）
├── scraper.py        # 爬虫核心（反爬、翻页、渲染）
├── exporter.py       # 数据导出
├── database.py       # SQLite 数据库
├── scheduler.py      # 应用内定时调度
├── picker.py         # 可视化选择器助手
├── dedup.py          # 数据去重
├── cleaner.py        # 数据清洗规则
├── templates.py      # 任务模板
├── subdomain.py      # 子域名收集
├── config.py         # 任务配置管理
├── requirements.txt  # 依赖
└── README.md         # 说明
```

## 注意事项

- 请遵守目标网站的 robots.txt 和相关法律法规。
- 不要高频请求，合理设置翻页延迟。
- 登录态信息请通过 Cookie 传入，注意保护隐私。
- 代理地址格式：`http://ip:port` 或 `https://ip:port`。
