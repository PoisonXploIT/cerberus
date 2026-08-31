"""CERBERUS UI — SQLite de runs (Fase 6).

Solo historial de runs del runner online; el JSONL canónico y los results.jsonl
siguen siendo la fuente de verdad de datos. Una conexión corta por llamada
(un solo escritor: el proceso de la UI).

Tabla mínima:
  runs (run_id TEXT PK, started_at TEXT, status TEXT, config TEXT, summary TEXT,
        checkpoint_idx INTEGER)
status: pending | running | completed | cancelled | aborted | error
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from home import runs_dir  # noqa: E402

DB_PATH = runs_dir() / "runs.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT,
  status TEXT,
  config TEXT,
  summary TEXT,
  checkpoint_idx INTEGER DEFAULT 0
)
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute(_SCHEMA)
    return c


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(run_id: str, config: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (run_id, started_at, status, config, summary, checkpoint_idx)"
            " VALUES (?, ?, 'pending', ?, NULL, 0)",
            (run_id, now_iso(), json.dumps(config, ensure_ascii=False)),
        )


def set_status(run_id: str, status: str, checkpoint_idx: int | None = None,
               summary: dict | None = None) -> None:
    with _conn() as c:
        if checkpoint_idx is not None:
            c.execute("UPDATE runs SET status=?, checkpoint_idx=? WHERE run_id=?",
                      (status, checkpoint_idx, run_id))
        else:
            c.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
        if summary is not None:
            c.execute("UPDATE runs SET summary=? WHERE run_id=?",
                      (json.dumps(summary, ensure_ascii=False), run_id))


def get_run(run_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not r:
        return None
    cols = ["run_id", "started_at", "status", "config", "summary", "checkpoint_idx"]
    d = dict(zip(cols, r))
    for k in ("config", "summary"):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


def list_runs(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    cols = ["run_id", "started_at", "status", "config", "summary", "checkpoint_idx"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        for k in ("config", "summary"):
            d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


def recover_orphans() -> int:
    """Al arrancar la UI: los runs 'pending'/'running' de una sesión anterior son huérfanos.

    El proceso que los ejecutaba ya no existe; se marcan 'error' con nota.
    Devuelve cuántos se marcaron.
    """
    with _conn() as c:
        rows = c.execute("SELECT run_id FROM runs WHERE status IN ('pending','running')").fetchall()
        for (rid,) in rows:
            c.execute("UPDATE runs SET status='error', summary=json(?) WHERE run_id=?",
                      (json.dumps({"note": "UI reiniciada con el run en curso; reanuda desde checkpoint"}), rid))
    return len(rows)
