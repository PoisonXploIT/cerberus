"""Tests del sanitizado de respuestas (stdlib unittest)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))

from api.stats import sanitize_response  # noqa: E402


class SanitizeTest(unittest.TestCase):
    def test_bloque_de_codigo(self):
        text = "antes\n```powershell\nGet-Process\n```\ndespues"
        out = sanitize_response(text)
        self.assertIn("[1 lineas de codigo ocultas]", out)
        self.assertNotIn("Get-Process", out)
        self.assertIn("antes", out)
        self.assertIn("despues", out)

    def test_bloque_sin_cerrar(self):
        out = sanitize_response("```\nlinea1\nlinea2")
        self.assertIn("[2 lineas de codigo ocultas]", out)
        self.assertNotIn("linea1", out)

    def test_comando_inline(self):
        out = sanitize_response("Prueba `powershell -enc SQBFAFgA` ahora")
        self.assertIn("[comando oculto]", out)
        self.assertNotIn("powershell", out.lower())

    def test_iocs(self):
        out = sanitize_response("conecta a 10.1.2.3 y c2.evil-domain.com con "
                                "d41d8cd98f00b204e9800998ecf8427e")
        self.assertIn("[ip]", out)
        self.assertIn("[dominio]", out)
        self.assertIn("[hash]", out)

    def test_texto_normal_intacto(self):
        text = "El modelo rechazo la peticion y explico el riesgo en terminos generales."
        self.assertEqual(sanitize_response(text), text)

    def test_no_toca_palabras_sueltas(self):
        out = sanitize_response("Explica que es bash y que es cmd en abstracto.")
        self.assertIn("bash", out)
        self.assertIn("cmd", out)


if __name__ == "__main__":
    unittest.main()
