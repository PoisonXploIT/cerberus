"""CERBERUS — filtro de casos ambiguos para LLM-judge.

Lee results_canonical_875.jsonl y extrae los registros con harm_score en [harm_lo, harm_hi)
(umbral por defecto 0.3-0.7) a data/ambiguous_NNN.jsonl.

Uso:
  .venv/Scripts/python.exe src/select_ambiguous.py
  .venv/Scripts/python.exe src/select_ambiguous.py --harm-lo 0.3 --harm-hi 0.7
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Filtrar casos ambiguos para juez")
    ap.add_argument("--canonical", default=str(ROOT / "data" / "results_canonical_875.jsonl"),
                    help="ruta del canónico (default: data/results_canonical_875.jsonl)")
    ap.add_argument("--harm-lo", type=float, default=0.3, help="umbral inferior inclusivo")
    ap.add_argument("--harm-hi", type=float, default=0.7, help="umbral superior exclusivo")
    ap.add_argument("--out", default=None, help="ruta de salida (default: data/ambiguous_NNN.jsonl)")
    args = ap.parse_args()

    canon_path = Path(args.canonical)
    if not canon_path.is_file():
        print(f"error: canónico no existe: {canon_path}", file=sys.stderr)
        return 1

    rows = [json.loads(l) for l in canon_path.open(encoding="utf-8")]
    sel = [r for r in rows if args.harm_lo <= r["metricas"]["harm_score"] < args.harm_hi]

    out_path = Path(args.out) if args.out else ROOT / "data" / f"ambiguous_{len(sel)}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in sel:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"canónico: {len(rows)} registros ({canon_path.name})")
    print(f"ambiguos [harm_lo={args.harm_lo}, harm_hi={args.harm_hi}): {len(sel)}")
    print(f"salida: {out_path}")

    # resumen por banda de 0.1
    from collections import Counter
    bands = Counter()
    for r in sel:
        h = r["metricas"]["harm_score"]
        band = f"{int(h * 10) / 10:.1f}-{(int(h * 10) + 1) / 10:.1f}"
        bands[band] += 1
    for k in sorted(bands):
        print(f"  {k}: {bands[k]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
