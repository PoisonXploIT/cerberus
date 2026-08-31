r"""Verificacion pre-push: ningun dato real en el arbol del repo.

Uso:  .venv\Scripts\python scripts\sanity_check.py
Salida 1 si aparece algun termino prohibido; ejecutarlo ANTES de cada push.

Notas de diseno:
  - Los terminos sueltos son substrings sin mayusculas/minusculas.
  - Se construyen por concatenacion para que ESTE fichero no se auto-pille.
  - "api_key" suelto daria falsos positivos en el codigo generico
    (judge_api_key como nombre de variable), por eso va como regex:
    solo pilla asignaciones a literal (posible key hardcodeada).
  - Los directorios data/, runs/, reports/ y logs/ se omiten: estan gitignoreados
    (datos de ejecucion que NUNCA entran al repo), asi que no son parte del arbol
    del repo aunque esten en disco.
  - Los ficheros >= 5 MB se omiten (no van al repo por .gitignore).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Nombres reales de modelo: nunca en codigo, docs, commits ni issues.
_WRN = "whiterabbit" + "neo"
_SK = "sk"
FORBIDDEN = [
    _WRN,
    "white " + "rabbit",
    "neo " + "rabbit",
    # Prefijos de keys de API (OpenRouter / OpenAI)
    _SK + "-or-",
    _SK + "-",
    # Nombre de env que no debe aparecer con valor
    "openai_" + "api_key",
]

FORBIDDEN_RE = [
    # api_key asignada a un literal: posible key hardcodeada en fichero.
    re.compile(r"api_key\s*=\s*[\"'][a-z0-9]{8,}"),
]

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".git", ".venv", "__pycache__"}
# Directorios gitignoreados: datos de ejecucion, nunca entran al repo.
SKIP_DIRS = {"data", "runs", "reports", "logs"}
MAX_SIZE = 5 * 1024 * 1024

fail = False
for path in ROOT.rglob("*"):
    if any(part in SKIP_PARTS or part in SKIP_DIRS for part in path.parts):
        continue
    try:
        if not path.is_file() or path.stat().st_size >= MAX_SIZE:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    low = text.lower()
    for term in FORBIDDEN:
        if term in low:
            print(f"FORBIDDEN '{term}' en {path.relative_to(ROOT)}")
            fail = True
    for rx in FORBIDDEN_RE:
        if rx.search(low):
            print(f"FORBIDDEN_RE {rx.pattern!r} en {path.relative_to(ROOT)}")
            fail = True

if fail:
    sys.exit(1)
print("OK: no forbidden terms found")
