"""CERBERUS — muestreo para validacion humana del juez.

Extrae N aleatorios de cada banda (0.3-0.4, 0.4-0.5, 0.5-0.6, 0.6-0.7) del canónico
y genera un markdown con prompt truncado + respuesta truncada + scores para que
un humano revise en 5 min si el juez se volvio loco.

Uso:
  .venv/Scripts/python.exe src/validate_judge.py --n 10
  .venv/Scripts/python.exe src/validate_judge.py --n 10 --judge-run runs/run_XXXX
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _truncate(s: str, n: int = 400) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n... [{len(s)-n} chars mas]"


def main() -> int:
    ap = argparse.ArgumentParser(description="Muestreo para validacion humana")
    ap.add_argument("--canonical", default=str(ROOT / "data" / "results_canonical_875.jsonl"))
    ap.add_argument("--judge-run", default=None, help="run_id o ruta (opcional, anota scores del juez)")
    ap.add_argument("--n", type=int, default=10, help="aleatorios por banda (default 10)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "data" / "validation_sample.md"))
    args = ap.parse_args()

    random.seed(args.seed)
    canon_path = Path(args.canonical)
    rows = [json.loads(l) for l in canon_path.open(encoding="utf-8")]

    # Cargar juez si hay run
    judge_rows: dict[tuple, dict] = {}
    if args.judge_run:
        p = Path(args.judge_run)
        if not p.is_file():
            candidate = ROOT / "runs" / args.judge_run / "results.jsonl"
            p = candidate if candidate.is_file() else None
        if p and p.is_file():
            for line in p.open(encoding="utf-8"):
                r = json.loads(line)
                judge_rows[(r["mitre_tactic"], r["mitre_technique"])] = r

    # Bandas
    bands: dict[str, list[dict]] = {"0.3-0.4": [], "0.4-0.5": [], "0.5-0.6": [], "0.6-0.7": []}
    for r in rows:
        h = r["metricas"]["harm_score"]
        if 0.3 <= h < 0.4: bands["0.3-0.4"].append(r)
        elif 0.4 <= h < 0.5: bands["0.4-0.5"].append(r)
        elif 0.5 <= h < 0.6: bands["0.5-0.6"].append(r)
        elif 0.6 <= h < 0.7: bands["0.6-0.7"].append(r)

    out_lines = [f"# Validacion humana — muestreo juez ({args.n} por banda)", ""]
    for band, recs in sorted(bands.items()):
        sample = random.sample(recs, min(args.n, len(recs)))
        out_lines.append(f"## Banda {band} ({len(recs)} total, {len(sample)} muestreados)")
        out_lines.append("")
        for i, r in enumerate(sample, 1):
            key = (r["mitre_tactic"], r["mitre_technique"])
            jrow = judge_rows.get(key)
            harm_h = r["metricas"]["harm_score"]
            harm_j = jrow["harm_judge"] if jrow else None
            out_lines.append(f"### {i}. {r['mitre_technique']} ({r['mitre_tactic']})")
            out_lines.append(f"- harm_heuristic: {harm_h}")
            if jrow:
                out_lines.append(f"- harm_judge: {harm_j} (conf={jrow.get('judge_confidence', '?')}, cat={jrow.get('judge_category', '?')})")
                out_lines.append(f"- judge_reason: {jrow.get('judge_reason', '')}")
            else:
                out_lines.append(f"- harm_judge: (sin ejecutar)")
            out_lines.append(f"- prompt: {_truncate(r['prompt_original'], 200)}")
            out_lines.append(f"- respuesta: {_truncate(r['respuesta_cruda'], 400)}")
            out_lines.append("")

    out_path = Path(args.out)
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"muestreo: {args.n} por banda, seed={args.seed}")
    for band, recs in sorted(bands.items()):
        print(f"  {band}: {len(recs)} en canónico, {min(args.n, len(recs))} muestreados")
    print(f"salida: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
