"""Offline smoke tests for core parsing and reporting behavior."""

import json
import tempfile
import unittest
from pathlib import Path

from recon_core import Asset, enrich_rdap, root_domain
from v4_js import extract_html_endpoints
from v4_reporting import report_from_rows
from exporter import export_json
from v4_providers import shodan_host, fofa_search


class CoreSmokeTests(unittest.TestCase):
    def test_url_and_ip_normalization(self):
        self.assertEqual(root_domain("https://a.example.com:8443/x"), "example.com")
        self.assertEqual(root_domain("198.18.2.77"), "198.18.2.77")

    def test_inline_endpoint_extraction(self):
        html = '<script>fetch("https://example.com/api/items")</script>'
        self.assertIn("https://example.com/api/items", extract_html_endpoints(html, "https://example.com/"))

    def test_rdap_skips_ip(self):
        self.assertEqual(enrich_rdap(Asset("127.0.0.1", "test")).whois_org, "")

    def test_report_and_export_complex_rows(self):
        rows = [{"type": "asset", "items": ["a", "b"], "meta": {"ok": True}}]
        report = report_from_rows("example.com", rows)
        with tempfile.TemporaryDirectory() as folder:
            report.write_html(str(Path(folder) / "report.html"))
            export_json(rows, str(Path(folder) / "rows.json"))
            self.assertTrue(json.loads(Path(folder, "rows.json").read_text(encoding="utf-8")))

    def test_provider_configuration_failures_are_local(self):
        self.assertFalse(shodan_host("192.0.2.1", "")["ok"])
        self.assertFalse(fofa_search('domain="example.com"', "abcdefgh")["ok"])


if __name__ == "__main__":
    unittest.main()
