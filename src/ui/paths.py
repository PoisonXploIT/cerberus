"""CERBERUS UI — rutas de runs con validacion estricta.

Un `run_id` llega por cuerpo o por path y se usa para formar rutas de disco.
Aqui se valida una sola vez y se garantiza que el resultado queda dentro de
`runs/`: nada de `..`, rutas absolutas ni nombres con separadores.
"""
from __future__ import annotations

import re
from pathlib import Path

from home import runs_dir

# Sin separadores, sin espacios, sin puntos suspensivos. 1-64 caracteres.
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InvalidRunId(ValueError):
    """El run_id no cumple el formato o escaparia de runs/."""


def validate_run_id(run_id: str | None) -> str:
    rid = run_id if isinstance(run_id, str) else ""
    if not rid or rid != rid.strip():
        raise InvalidRunId("run_id vacio o con espacios en los extremos")
    if ".." in rid or rid.startswith(".") or not SAFE_RUN_ID.match(rid):
        raise InvalidRunId(f"run_id invalido: {rid!r} (usa letras, numeros, punto, guion y _)")
    return rid


def run_dir(run_id: str, create: bool = False) -> Path:
    """Directorio del run, siempre hijo directo de runs/."""
    rid = validate_run_id(run_id)
    base = runs_dir().resolve()
    path = (base / rid).resolve()
    if path.parent != base:
        raise InvalidRunId(f"run_id fuera de runs/: {rid!r}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
