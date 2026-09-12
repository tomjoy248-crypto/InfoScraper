"""示例：收集 example.com 的子域名"""
from subdomain import collect_subdomains

results = collect_subdomains(
    domain="example.com",
    enable_brute=True,
    enable_crtsh=True,
    threads=50,
    on_progress=lambda cur, total: print(f"进度: {cur}/{total}"),
    on_log=lambda msg: print(f"[日志] {msg}"),
)

print(f"\n共发现 {len(results)} 个子域名")
for r in results[:20]:
    print(r)
