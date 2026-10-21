"""Release checks: one version everywhere, web UI hardening (no network, no model).

Run: PYTHONPATH=. venv/bin/python -P -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

_TMP_HOME = tempfile.mkdtemp(prefix="taxclaw-test-home-")
os.environ["HOME"] = _TMP_HOME

from src import __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_semver(self) -> None:
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_skill_md_metadata_version_matches(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        m = re.search(r'^\s+version:\s*"([^"]+)"', front, re.M)
        self.assertIsNotNone(m, "metadata.version missing from SKILL.md frontmatter")
        self.assertEqual(m.group(1), __version__)

    def test_runbook_heading_matches(self) -> None:
        first = (ROOT / "RUNBOOK.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, f"# TaxClaw v{__version__} Runbook")

    def test_changelog_has_release_section(self) -> None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(text, rf"(?m)^## {re.escape(__version__)} - ")

    def test_code_uses_package_version(self) -> None:
        from src.exporter import TAXCLAW_VERSION
        from src.main import app

        self.assertEqual(TAXCLAW_VERSION, __version__)
        self.assertEqual(app.version, __version__)

    def test_no_stale_hardcoded_versions(self) -> None:
        stale = re.compile(r"\b0\.1\.[0-9]\b")
        for rel in ("SKILL.md", "RUNBOOK.md", "README.md", "setup.sh", "src/main.py", "src/exporter.py", "src/mcp_server.py", "src/cli.py"):
            self.assertIsNone(stale.search((ROOT / rel).read_text(encoding="utf-8")), rel)

    def test_cli_version_flag(self) -> None:
        from src.cli import build_parser

        with self.assertRaises(SystemExit) as cm, open(os.devnull, "w") as devnull:
            import contextlib

            with contextlib.redirect_stdout(devnull):
                build_parser().parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)


class WebHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        from src.main import app

        cls.app = app
        cls.client = TestClient(app, base_url="http://127.0.0.1:8421")

    def test_get_with_foreign_host_is_refused(self) -> None:
        # DNS rebinding: the browser sends the attacker's hostname in Host.
        for path in ("/", "/documents", "/api/stats", "/settings", "/review"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
            r = self.client.get(path, headers={"host": "attacker.example:8421"})
            self.assertEqual(r.status_code, 403, path)

    def test_get_with_foreign_origin_is_refused(self) -> None:
        r = self.client.get("/api/stats", headers={"origin": "http://attacker.example"})
        self.assertEqual(r.status_code, 403)

    def test_loopback_hosts_allowed(self) -> None:
        for host in ("127.0.0.1:8421", "localhost:8421", "[::1]:8421", "taxclaw.localhost:8421"):
            r = self.client.get("/api/stats", headers={"host": host})
            self.assertEqual(r.status_code, 200, host)
        r = self.client.get("/api/stats", headers={"origin": "http://127.0.0.1:8421"})
        self.assertEqual(r.status_code, 200)

    def test_security_headers(self) -> None:
        r = self.client.get("/")
        csp = r.headers.get("content-security-policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")

    def test_templates_load_no_remote_scripts_or_styles(self) -> None:
        remote = re.compile(r"<(script|link)[^>]+(src|href)\s*=\s*[\"']?(https?:)?//", re.I)
        for p in sorted((ROOT / "templates").glob("*.html")):
            self.assertIsNone(remote.search(p.read_text(encoding="utf-8")), p.name)

    def test_contact_page_discloses_formspree(self) -> None:
        html = self.client.get("/contact").text
        self.assertIn("Formspree", html)
        self.assertIn("leaves your machine", html)


if __name__ == "__main__":
    unittest.main()
