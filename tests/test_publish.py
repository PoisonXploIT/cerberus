"""Tests del publicador del sitio (auditoria y payload)."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
sys.path.insert(0, str(ROOT / "src" / "ui" / "api"))

import publish_site  # noqa: E402
import stats as site_stats  # noqa: E402

CLEAN = {
    "schema": 1,
    "generated_at": "2026-10-23T10:00:00+00:00",
    "run_id": "run_1",
    "label": "modelo local",
    "total": 2,
    "harm": {"mean": 0.5, "median": 0.5, "min": 0.3, "max": 0.7},
    "buckets": {"<0.3": 0, "0.3-0.5": 1, "0.5-0.7": 1, ">=0.7": 0},
    "detail_level": {"0": 0, "1": 0, "2": 1, "3": 1, "4": 0, "5": 0},
    "estados": {"success": 2},
    "latency_ms": {"median": 100, "p95": 200},
    "tokens_out_mean": 50,
    "tactics": [{"tactic": "Execution", "prompts": 2, "harm_mean": 0.5,
                 "pct_ge_0_7": 0.0}],
    "techniques": [
        {"tactic": "Execution", "technique": "T1059", "subtechnique": "001",
         "harm": 0.4, "detail": 3},
        {"tactic": "Execution", "technique": "T1053", "subtechnique": "",
         "harm": 0.6, "detail": 2},
    ],
    "dropped_fields": 20,
}


class AuditTest(unittest.TestCase):
    def test_payload_limpio_pasa(self):
        self.assertEqual(publish_site.audit(copy.deepcopy(CLEAN)), [])

    def test_campo_prohibido(self):
        bad = copy.deepcopy(CLEAN)
        bad["techniques"][0]["prompt"] = "hola"
        self.assertTrue(any("prohibido" in i for i in publish_site.audit(bad)))

    def test_ruta_windows(self):
        bad = copy.deepcopy(CLEAN)
        bad["label"] = r"C:\Users\alguien\modelo"
        issues = publish_site.audit(bad)
        self.assertTrue(any("ruta" in i for i in issues), issues)

    def test_ip(self):
        bad = copy.deepcopy(CLEAN)
        bad["tactics"][0]["tactic"] = "10.0.0.5"
        self.assertTrue(any("IP" in i for i in publish_site.audit(bad)))

    def test_url(self):
        bad = copy.deepcopy(CLEAN)
        bad["label"] = "http://localhost:8085/v1"
        issues = publish_site.audit(bad)
        self.assertTrue(any("URL" in i or "localhost" in i for i in issues), issues)

    def test_token(self):
        bad = copy.deepcopy(CLEAN)
        bad["label"] = "s" + "k-abcdefgh12345678"
        self.assertTrue(any("token" in i for i in publish_site.audit(bad)))

    def test_cadena_larga(self):
        bad = copy.deepcopy(CLEAN)
        bad["tactics"][0]["tactic"] = "A" * 200
        self.assertTrue(any("larga" in i for i in publish_site.audit(bad)))

    def test_clave_extra(self):
        bad = copy.deepcopy(CLEAN)
        bad["extra"] = 1
        self.assertTrue(any("no permitidas" in i for i in publish_site.audit(bad)))

    def test_numero_no_finito(self):
        bad = copy.deepcopy(CLEAN)
        bad["harm"]["mean"] = float("inf")
        self.assertTrue(any("finito" in i for i in publish_site.audit(bad)))

    def test_tecnica_con_clave_extra(self):
        bad = copy.deepcopy(CLEAN)
        bad["techniques"][0]["respuesta"] = "x"
        self.assertTrue(any("techniques[0]" in i for i in publish_site.audit(bad)))


@unittest.skipUnless(site_stats.canonical_source(), "sin data/ en este entorno")
class PayloadTest(unittest.TestCase):
    def test_payload_real_sin_texto(self):
        p = publish_site.build_payload(None, "modelo local")
        self.assertEqual(p["total"], len(p["techniques"]))
        self.assertEqual(publish_site.audit(p), [])
        for t in p["techniques"]:
            self.assertLessEqual(set(t), publish_site.TECH_KEYS)
            self.assertNotIn("prompt", t)
            self.assertNotIn("respuesta", t)

    def test_config_rechaza_dominio_externo(self):
        with self.assertRaises(publish_site.PublishError):
            publish_site.validate_config({"site_repo": str(ROOT), "project": "cerberus",
                                          "domain": "cerberus.ejemplo.com",
                                          "label": "x"})

    def test_config_rechaza_proyecto_invalido(self):
        with self.assertRaises(publish_site.PublishError):
            publish_site.validate_config({"site_repo": str(ROOT), "project": "../x",
                                          "domain": "cerberus.sammideblas.com",
                                          "label": "x"})


if __name__ == "__main__":
    unittest.main()
