"""CERBERUS UI — carpeta base de datos (home).

Por defecto el home es la raiz del proyecto; CERBERUS_HOME permite apuntar a
otro arbol (pruebas con estado vacio, despliegues sin datos). La UI nunca
hardcodea nombres de fichero concretos: todo se resuelve contra el home.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_HOME = Path(__file__).resolve().parents[2]


def home_dir() -> Path:
    return Path(os.environ.get("CERBERUS_HOME", str(_DEFAULT_HOME))).resolve()


def data_dir() -> Path:
    return home_dir() / "data"


def runs_dir() -> Path:
    return home_dir() / "runs"


def reports_dir() -> Path:
    return home_dir() / "reports"
