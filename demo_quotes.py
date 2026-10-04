"""示例：采集 quotes.toscrape.com 的名言"""
from scraper import WebScraper
from exporter import export

scraper = WebScraper(
    start_url="http://quotes.toscrape.com/",
    delay=1.0,
    delay_random=True,
)

data = scraper.run(
    list_selector=".quote",
    fields=[
        {"name": "名言", "selector": ".text", "attr": None},
        {"name": "作者", "selector": ".author", "attr": None},
        {"name": "链接", "selector": "a", "attr": "href"},
    ],
    selector_type="css",
    max_pages=2,
    next_page_selector=".next a",
    next_page_mode="url",
    on_progress=lambda p, total: print(f"第 {p} 页完成，累计 {total} 条"),
    on_log=lambda msg: print(f"[日志] {msg}"),
)
scraper.close()

print(f"\n共采集 {len(data)} 条")
for row in data[:3]:
    print(row)

export(data, "quotes_demo.xlsx")
print("已导出到 quotes_demo.xlsx")
