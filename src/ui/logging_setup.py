"""Log estructurado con rotacion para la UI (sin prompts ni respuestas)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from home import home_dir

_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(level: int = logging.INFO) -> Path:
    """Configura logs/ui.log (1 MB x 3) y devuelve la ruta."""
    log_dir = home_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "ui.log"

    root = logging.getLogger("cerberus")
    root.setLevel(level)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FMT))
        root.addHandler(handler)
    return path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("cerberus." + name)
