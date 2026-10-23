"""Tests de las defensas de la UI (stdlib unittest, sin dependencias).

Se ejecutan sin levantar la app:

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))

import paths  # noqa: E402
import security  # noqa: E402
import urls  # noqa: E402
from run_mitre_eval import safe_run_dir  # noqa: E402


class RunIdTest(unittest.TestCase):
    def test_ids_validos(self):
        for rid in ("run_20260830_010330", "ui_run_1", "a.b-c_9", "A" * 64):
            self.assertEqual(paths.validate_run_id(rid), rid)

    def test_traversal_rechazado(self):
        for rid in ("../x", "..", "../../etc", "a/b", "a\\b", ".hidden",
                    "run ", "run\n", "", " " * 3, "x" * 65, "/abs", "C:/tmp"):
            with self.assertRaises(paths.InvalidRunId, msg=rid):
                paths.validate_run_id(rid)

    def test_run_dir_dentro_de_runs(self):
        d = paths.run_dir("run_20260830_010330")
        self.assertEqual(d.parent, paths.runs_dir().resolve())

    def test_cli_y_ui_comparten_regla(self):
        with self.assertRaises(ValueError):
            safe_run_dir("../escape")
        self.assertEqual(safe_run_dir("ok_1").name, "ok_1")


class UrlTest(unittest.TestCase):
    def test_local_ok(self):
        for u in ("http://localhost:8085/v1", "http://127.0.0.1:8085/v1",
                  "http://[::1]:8085/v1"):
            self.assertEqual(urls.validate_local_base_url(u), u.rstrip("/"))

    def test_local_rechaza_remoto(self):
        for u in ("http://example.com/v1", "http://10.0.0.5:8085/v1",
                  "http://169.254.169.254/latest", "ftp://localhost/x",
                  "http://user:pass@localhost:8085/v1",
                  "http://localhost:8085/v1?x=1", "http://localhost:80", ""):
            with self.assertRaises(urls.BadUrl, msg=u):
                urls.validate_local_base_url(u)

    def test_judge_allowlist(self):
        self.assertEqual(urls.validate_judge_base_url("https://openrouter.ai/api/v1"),
                         "https://openrouter.ai/api/v1")
        for u in ("http://openrouter.ai/api/v1", "https://evil.example/v1",
                  "https://127.0.0.1.nip.io/v1", "https://openrouter.ai.evil.tld/v1"):
            with self.assertRaises(urls.BadUrl, msg=u):
                urls.validate_judge_base_url(u)

    def test_judge_loopback_http_para_tests(self):
        self.assertEqual(urls.validate_judge_base_url("http://127.0.0.1:8192/v1"),
                         "http://127.0.0.1:8192/v1")

    def test_judge_allowlist_por_env(self):
        import os

        os.environ["JUDGE_ALLOWED_HOSTS"] = "mi-proveedor.example"
        try:
            self.assertEqual(urls.validate_judge_base_url("https://mi-proveedor.example/v1"),
                             "https://mi-proveedor.example/v1")
        finally:
            os.environ.pop("JUDGE_ALLOWED_HOSTS", None)


class HostTest(unittest.TestCase):
    def test_hosts_locales(self):
        for h in ("127.0.0.1:8599", "localhost:8599", "[::1]:8599", "testserver"):
            self.assertTrue(security._host_ok(h), h)

    def test_hosts_externos(self):
        for h in ("evil.tld", "evil.tld:8599", "127.0.0.1.evil.tld", "", None,
                  "192.168.1.10:8599"):
            self.assertFalse(security._host_ok(h), h)

    def test_origin(self):
        self.assertTrue(security._origin_ok(None))
        self.assertTrue(security._origin_ok("http://127.0.0.1:8599"))
        self.assertFalse(security._origin_ok("http://evil.tld"))

    def test_token_persistente(self):
        t1 = security.ui_token()
        self.assertGreaterEqual(len(t1), 20)
        self.assertEqual(t1, security.ui_token())
        self.assertTrue((paths.runs_dir() / ".ui_token").exists())


class CspTest(unittest.TestCase):
    def test_csp_script_estricto(self):
        self.assertIn("default-src 'self'", security.CSP)
        self.assertIn("script-src 'self'", security.CSP)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", security.CSP)
        self.assertIn("frame-ancestors 'none'", security.CSP)


if __name__ == "__main__":
    unittest.main()
