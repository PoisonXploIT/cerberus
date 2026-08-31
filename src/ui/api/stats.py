"""CERBERUS UI — datos del ultimo results_*.jsonl o de un run concreto (Fase 5a).

Sin canónico hardcodeado: el dashboard se resuelve contra CERBERUS_HOME
(por defecto la raiz del proyecto) y sirve el ultimo results_*.jsonl de
data/ por mtime; si no hay ninguno, /api/stats devuelve {"status": "no_data"}.
Opcional ?run=<run_id> para poblar el panel con el results.jsonl de un run.
SQLite no interviene en estos endpoints; solo archivos JSONL.

Endpoints:
  GET /api/stats?run=<id>     métricas globales + por táctica para el dashboard.
  GET /api/results?run=<id>  filas compactas para la tabla (sin texto de respuesta).
  GET /api/results/{idx}?sanitize=1|0&run=<id>
                             detalle completo.

Seguridad (coherente acta 5): solo localhost, sin auth por diseño; el parámetro
run se valida para que no haya traversal fuera de runs/; los logs de la app
no imprimen respuestas completas por defecto.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from fastapi import APIRouter, HTTPException

from home import data_dir, runs_dir  # noqa: E402

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

NO_DATA = {
    "status": "no_data",
    "message": "No hay datos. Ejecuta un run o coloca un results_*.jsonl en data/",
}

router = APIRouter()


def canonical_source() -> Path | None:
    """Ultimo results_*.jsonl de data/ por mtime; None si no hay ninguno."""
    d = data_dir()
    if not d.is_dir():
        return None
    cands = [p for p in d.glob("results_*.jsonl") if p.is_file()]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def resolve_source(run: str) -> Path:
    """Fichero de un run concreto: runs/<run>/results.jsonl.

    El run_id se valida con regex y el path resuelto debe quedar dentro de
    runs/: ni '../' ni paths absolutos salen de la carpeta de runs.
    """
    if not _SAFE_RUN_ID.match(run):
        raise HTTPException(400, f"run_id inválido: {run!r}")
    base = runs_dir().resolve()
    path = (base / run / "results.jsonl").resolve()
    if not path.is_relative_to(base) or not path.exists():
        raise HTTPException(404, f"el run {run} no tiene results.jsonl")
    return path


_cache: dict[Path, tuple[float, list[dict]]] = {}


def load_rows(path: Path) -> list[dict]:
    """Carga el JSONL y lo cachea por (path, mtime): barato repintar el panel."""
    mtime = path.stat().st_mtime
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if len(_cache) >= 8:  # tope del caché: no dejar memoria sin límite
        _cache.clear()
    _cache[path] = (mtime, rows)
    return rows


def sanitize_response(text: str) -> str:
    """Oculta el contenido de los bloques de código (```...```) en modo demo.

    Conserva cabeceras, explicaciones y la firma del bloque; solo se sustituye
    el cuerpo de cada bloque por un marcador con el número de líneas ocultas.
    """
    out: list[str] = []
    in_fence = False
    hidden = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                out.append(line)
                hidden = 0
            else:
                out.append(f"[{hidden} lineas de codigo ocultas - modo sanitizado]")
                out.append("```")
                in_fence = False
            continue
        if in_fence:
            hidden += 1
        else:
            out.append(line)
    if in_fence and hidden:  # bloque sin cerrar al final
        out.append(f"[{hidden} lineas de codigo ocultas - modo sanitizado]")
    return "\n".join(out)


def _pct(values: list[float], p: float) -> float:
    """Percentil por índice sobre lista ordenada (sin numpy)."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(p * (len(s) - 1)))
    return s[idx]


def _bucket(harm: float) -> str:
    if harm < 0.3:
        return "<0.3"
    if harm < 0.5:
        return "0.3-0.5"
    if harm < 0.7:
        return "0.5-0.7"
    return ">=0.7"


def compute_stats(rows: list[dict], source_name: str = "") -> dict:
    if not rows:  # run lanzado pero sin registros aún
        return {
            "source": source_name or "(vacío)", "total": 0,
            "harm": {"mean": 0, "median": 0, "min": 0, "max": 0},
            "buckets": {"<0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, ">=0.7": 0},
            "detail_level": {str(i): 0 for i in range(6)},
            "latency_ms": {"median": 0, "p95": 0},
            "tokens_out_total": 0, "tokens_out_mean": 0,
            "estados": {}, "tactics": [],
        }
    harms = [r["metricas"]["harm_score"] for r in rows]
    lat = [r["metricas"]["latency_ms"] for r in rows]
    toks = [r["metricas"]["tokens_out"] for r in rows]

    buckets = {"<0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, ">=0.7": 0}
    for h in harms:
        buckets[_bucket(h)] += 1

    detail_dist = {str(i): 0 for i in range(6)}
    estados: dict[str, int] = {}
    for r in rows:
        detail_dist[str(r["metricas"]["detail_level"])] += 1
        estados[r["estado"]] = estados.get(r["estado"], 0) + 1

    tactics: dict[str, dict] = {}
    for r in rows:
        t = tactics.setdefault(
            r["mitre_tactic"],
            {"tactic": r["mitre_tactic"], "prompts": 0, "harm_sum": 0.0, "ge7": 0,
             "tok_sum": 0, "lat_sum": 0},
        )
        t["prompts"] += 1
        t["harm_sum"] += r["metricas"]["harm_score"]
        if r["metricas"]["harm_score"] >= 0.7:
            t["ge7"] += 1
        t["tok_sum"] += r["metricas"]["tokens_out"]
        t["lat_sum"] += r["metricas"]["latency_ms"]

    tactics_out = [
        {
            "tactic": t,
            "prompts": d["prompts"],
            "harm_mean": round(d["harm_sum"] / d["prompts"], 3),
            "pct_ge_0_7": round(100.0 * d["ge7"] / d["prompts"], 1),
            "tokens_mean": round(d["tok_sum"] / d["prompts"]),
            "latency_mean_ms": round(d["lat_sum"] / d["prompts"]),
        }
        for t, d in tactics.items()
    ]
    tactics_out.sort(key=lambda x: -x["harm_mean"])

    return {
        "source": source_name,
        "total": len(rows),
        "harm": {
            "mean": round(statistics.fmean(harms), 3),
            "median": round(statistics.median(harms), 3),
            "min": min(harms),
            "max": max(harms),
        },
        "buckets": buckets,
        "detail_level": detail_dist,
        "latency_ms": {"median": round(statistics.median(lat)), "p95": round(_pct(lat, 0.95))},
        "tokens_out_total": sum(toks),
        "tokens_out_mean": round(statistics.fmean(toks)),
        "estados": estados,
        "tactics": tactics_out,
    }


@router.get("/api/health")
def health() -> dict:
    src = canonical_source()
    return {"ok": True, "source": src.name if src else "no_data"}


@router.get("/api/stats")
def stats(run: str | None = None) -> dict:
    if run is not None:
        p = resolve_source(run)
        return compute_stats(load_rows(p), p.name)
    src = canonical_source()
    if src is None:
        return NO_DATA
    return compute_stats(load_rows(src), src.name)


@router.get("/api/results")
def results(run: str | None = None) -> list[dict]:
    if run is not None:
        rows = load_rows(resolve_source(run))
    else:
        src = canonical_source()
        if src is None:
            return []
        rows = load_rows(src)
    return [
        {
            "i": i,
            "tactic": r["mitre_tactic"],
            "technique": r["mitre_technique"],
            "subtechnique": r["mitre_subtechnique"],
            "estado": r["estado"],
            "harm": r["metricas"]["harm_score"],
            "detail": r["metricas"]["detail_level"],
            "tokens_out": r["metricas"]["tokens_out"],
            "latency_ms": r["metricas"]["latency_ms"],
        }
        for i, r in enumerate(rows)
    ]


@router.get("/api/results/{idx}")
def result_detail(idx: int, sanitize: bool = True, run: str | None = None) -> dict:
    if run is not None:
        rows = load_rows(resolve_source(run))
    else:
        src = canonical_source()
        if src is None:
            raise HTTPException(404, "sin datos: no hay results_*.jsonl en data/")
        rows = load_rows(src)
    if idx < 0 or idx >= len(rows):
        raise HTTPException(status_code=404, detail=f"idx {idx} fuera de rango (0-{len(rows)-1})")
    r = rows[idx]
    resp_cruda = r["respuesta_cruda"]
    resp_proc = r["respuesta_procesada"]
    if sanitize:
        resp_cruda = sanitize_response(resp_cruda)
        resp_proc = sanitize_response(resp_proc)
    return {
        "i": idx,
        "tactic": r["mitre_tactic"],
        "technique": r["mitre_technique"],
        "subtechnique": r["mitre_subtechnique"],
        "estado": r["estado"],
        "prompt_original": r["prompt_original"],
        "prompt_enviado": r["prompt_enviado"],
        "respuesta_cruda": resp_cruda,
        "respuesta_procesada": resp_proc,
        "metricas": r["metricas"],
        "hash_respuesta": r.get("hash_respuesta"),
        "run_id": r.get("run_id"),
        "modelo_local": r.get("modelo_local"),
        "sanitized": bool(sanitize),
    }
