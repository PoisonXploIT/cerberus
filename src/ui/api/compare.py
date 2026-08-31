"""CERBERUS UI — comparativa de runs.

GET /api/runs/{a}/compare/{b}  -> stats de ambos runs (heuristic y, si el run
fue puntuado con juez, harm_final) + tabla por tactica para ver la diferencia.

Lee los results.jsonl / results_merged.jsonl de runs/<id>/; no toca el
canonico ni la BD.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException  # noqa: E402

from home import runs_dir  # noqa: E402

RUNS_DIR = runs_dir()

router = APIRouter()


@router.get("/api/runs/scan")
def scan_runs() -> list[dict]:
    """Runs en disco con results.jsonl (incluye los hechos por CLI, que no estan en la BD)."""
    out = []
    if RUNS_DIR.is_dir():
        for d in sorted(RUNS_DIR.iterdir(), reverse=True):
            if d.is_dir() and (d / "results.jsonl").is_file():
                out.append({
                    "run_id": d.name,
                    "has_merged": (d / "results_merged.jsonl").is_file(),
                })
    return out


def _buckets(vals: list[float]) -> dict[str, int]:
    b = Counter()
    for v in vals:
        if v >= 0.7:
            b[">=0.7"] += 1
        elif v >= 0.5:
            b["0.5-0.7"] += 1
        elif v >= 0.3:
            b["0.3-0.5"] += 1
        else:
            b["<0.3"] += 1
    return dict(b)


def _dist(vals: list[float]) -> dict:
    if not vals:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(statistics.fmean(vals), 3),
        "median": round(statistics.median(vals), 3),
        "min": min(vals),
        "max": max(vals),
    }


def _run_stats(run_id: str) -> dict:
    run_dir = RUNS_DIR / run_id
    results = run_dir / "results.jsonl"
    if not results.is_file():
        raise HTTPException(status_code=404, detail=f"{run_id}: sin results.jsonl")
    with results.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    heur = [r["metricas"]["harm_score"] for r in rows]
    st: dict = {
        "run_id": run_id,
        "total": len(rows),
        "harm_heuristic": _dist(heur),
        "buckets_heuristic": _buckets(heur),
        "tactics": {},
    }
    for r in rows:
        t = st["tactics"].setdefault(r["mitre_tactic"], {"n": 0, "sum": 0.0})
        t["n"] += 1
        t["sum"] += r["metricas"]["harm_score"]

    merged = run_dir / "results_merged.jsonl"
    if merged.is_file():
        with merged.open(encoding="utf-8") as f:
            mrows = [json.loads(line) for line in f if line.strip()]
        final = [r["metricas"]["harm_final"] for r in mrows]
        judged = sum(1 for r in mrows if r["metricas"].get("harm_judge") is not None)
        upgraded = sum(
            1 for r in mrows
            if (r["metricas"].get("harm_judge") or 0) > r["metricas"]["harm_heuristic"]
        )
        st.update({
            "has_judge": True,
            "judged": judged,
            "upgraded_by_judge": upgraded,
            "harm_final": _dist(final),
            "buckets_final": _buckets(final),
        })
    else:
        st["has_judge"] = False

    # media por tactica (heuristic; el merged conserva el mismo orden que results)
    for t in list(st["tactics"]):
        d = st["tactics"][t]
        d["harm_mean"] = round(d["sum"] / d["n"], 3) if d["n"] else 0.0
        del d["sum"]
    return st


@router.get("/api/runs/{a}/compare/{b}")
def compare_runs(a: str, b: str) -> dict:
    if a == b:
        raise HTTPException(status_code=422, detail="Elige dos runs distintos")
    sa, sb = _run_stats(a), _run_stats(b)

    per_tactic = []
    for t in sorted(set(sa["tactics"]) | set(sb["tactics"])):
        ta, tb = sa["tactics"].get(t), sb["tactics"].get(t)
        per_tactic.append({
            "tactic": t,
            "a_n": ta["n"] if ta else 0,
            "a_mean": ta["harm_mean"] if ta else None,
            "b_n": tb["n"] if tb else 0,
            "b_mean": tb["harm_mean"] if tb else None,
            "diff": (round(ta["harm_mean"] - tb["harm_mean"], 3)
                     if ta and tb else None),
        })

    # Diff técnica a técnica: la union de tecnicas de ambos runs, ordenada por |diff|.
    def tech_map(run_id: str) -> dict[tuple, float]:
        out: dict[tuple, float] = {}
        with (RUNS_DIR / run_id / "results.jsonl").open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out[(r["mitre_tactic"], r["mitre_technique"])] = r["metricas"]["harm_score"]
        return out

    ma, mb = tech_map(a), tech_map(b)
    per_technique = []
    for key in sorted(set(ma) | set(mb)):
        ha, hb = ma.get(key), mb.get(key)
        per_technique.append({
            "tactic": key[0],
            "technique": key[1],
            "a_harm": ha,
            "b_harm": hb,
            "diff": round(ha - hb, 3) if ha is not None and hb is not None else None,
        })
    per_technique.sort(key=lambda r: (r["diff"] is None, -(abs(r["diff"]) if r["diff"] is not None else 0)))

    return {
        "a": sa,
        "b": sb,
        "per_tactic": per_tactic,
        "per_technique": per_technique,
        "note": ("diff = A - B (heuristic). Si un run fue puntuado con juez, mira harm_final: "
                 "regla conservadora, el juez solo sube. per_technique va ordenada por |diff|."),
    }
