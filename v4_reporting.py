"""Structured findings and HTML reporting for authorized assessments."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


@dataclass
class Finding:
    category: str
    title: str
    target: str
    severity: str = "info"
    evidence: str = ""
    recommendation: str = ""
    source: str = "local"


@dataclass
class AssessmentReport:
    target: str
    findings: List[Finding] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def to_json(self) -> str:
        return json.dumps({"target": self.target, "created_at": self.created_at,
                           "findings": [asdict(item) for item in self.findings]},
                          ensure_ascii=False, indent=2)

    def write_html(self, path: str) -> None:
        categories = {}
        failures = []
        for item in self.findings:
            categories[item.title] = categories.get(item.title, 0) + 1
            if "unreachable" in item.evidence.lower() or "失败" in item.evidence:
                failures.append(item.target)
        summary = "；".join(f"{html.escape(str(k))}: {v}" for k, v in sorted(categories.items())) or "无资产"
        failed_html = "、".join(html.escape(str(x)) for x in failures[:100]) or "无"
        rows = []
        for item in self.findings:
            rows.append("<tr>" + "".join(
                f"<td>{html.escape(str(value))}</td>" for value in
                (item.category, item.title, item.target, item.severity,
                 item.evidence, item.recommendation, item.source)
            ) + "</tr>")
        document = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>安全评估报告</title><style>body{font-family:Arial,sans-serif;margin:2rem}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:.45rem;text-align:left;vertical-align:top}
th{background:#f2f2f2}.high{color:#b00020}.medium{color:#9a6700}.low{color:#176b2c}</style>
<h1>安全评估报告</h1><p>目标：{target}</p><p>生成时间：{created}</p>
<h2>采集摘要</h2><p>总记录：{total}；类型统计：{summary}</p><p>失败或不可达目标：{failed}</p>
<table><thead><tr><th>类别</th><th>标题</th><th>目标</th><th>等级</th><th>证据</th><th>建议</th><th>来源</th></tr></thead>
<tbody>{rows}</tbody></table></html>""".format(
            target=html.escape(self.target), created=html.escape(self.created_at),
            total=len(self.findings), summary=summary, failed=failed_html, rows="".join(rows)
        )
        Path(path).write_text(document, encoding="utf-8")

    def write_pdf(self, path: str) -> None:
        """Render the same report to PDF using the optional Playwright runtime."""
        import tempfile
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as folder:
            html_path = Path(folder) / "report.html"
            self.write_html(str(html_path))
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                page.pdf(path=path, format="A4", print_background=True)
                browser.close()


def report_from_rows(target: str, rows: Iterable[dict]) -> AssessmentReport:
    report = AssessmentReport(target)
    for row in rows:
        report.add(Finding(category="asset", title=str(row.get("type", "asset")),
                           target=str(row.get("url", row.get("子域名", ""))),
                           evidence=json.dumps(row, ensure_ascii=False)))
    return report
