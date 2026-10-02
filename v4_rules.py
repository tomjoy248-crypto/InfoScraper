"""Non-destructive HTTP configuration checks."""

from __future__ import annotations

from typing import Iterable, List

from v4_reporting import Finding


def check_asset(row: dict) -> List[Finding]:
    target = str(row.get("最终URL") or row.get("url") or row.get("子域名") or "")
    findings: List[Finding] = []
    headers = str(row.get("安全头") or "")
    if "missing:" in headers.lower() and "strict-transport-security" in headers.lower():
        findings.append(Finding("headers", "HSTS header missing", target, "low", headers,
                                "HTTPS sites should send Strict-Transport-Security."))
    if "missing:" in headers.lower() and "content-security-policy" in headers.lower():
        findings.append(Finding("headers", "Content-Security-Policy header missing", target, "low", headers,
                                "Define a restrictive Content-Security-Policy."))
    if target.lower().startswith("http://"):
        findings.append(Finding("transport", "HTTP URL observed", target, "info", target,
                                "Prefer HTTPS and redirect HTTP to HTTPS."))
    return findings


def evaluate(rows: Iterable[dict]) -> List[Finding]:
    findings: List[Finding] = []
    for row in rows:
        findings.extend(check_asset(row))
    return findings
