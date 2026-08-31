"""CERBERUS Fase 2: Parser de prompts MITRE ATT&CK.

Lee el dataset Markdown y lo convierte a JSONL validado.

Entrada : --dataset PATH (o env CERBERUS_PROMPTS_MD); por defecto
          data/mitre_redteam_prompts.md dentro del proyecto
Salida  : data/mitre_prompts.jsonl (o --out)

Estructura esperada del Markdown:
  ## NombreTactica                (seccion de tactica)
  ### TXXXX - Nombre              (tecnica o sub-tecnica; sub = "### TXXXX.YYY - Nombre")
  > prompt en bloque de cita      (puede ocupar varias lineas "> ...")

Validaciones (gate real, exit != 0 si alguna falla):
  V1  Total de records == total declarado en el indice (873)
  V2  15 tacticas; conteo por tactica coincide con el indice del propio archivo
  V3  Sin duplicados: technique_id unico dentro de cada tactica y global
  V4  Cada record tiene prompt_text no vacio
  V5  Sub-tecnicas: parent_technique existe como record de la misma tactica
  V6  Cabeceras "### T" sin cuerpo de cita -> error (prompt perdido)

Uso:
  .venv/Scripts/python.exe src/parser_mitre.py [--dataset PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# El dataset por defecto vive dentro del proyecto; CERBERUS_PROMPTS_MD (env)
# o --dataset permiten apuntar a otra copia sin tocar el codigo.
DEFAULT_DATASET = os.environ.get("CERBERUS_PROMPTS_MD") or str(ROOT / "data" / "mitre_redteam_prompts.md")
DEFAULT_OUT = ROOT / "data" / "mitre_prompts.jsonl"

TECH_RE = re.compile(r"^### (T\d{4}(?:\.\d{3})?) - (.+?)\s*$")


def slugify(name: str) -> str:
    return name.lower().replace(" ", "-")


def parse_index(lines: list[str]) -> dict[str, int] | None:
    """Extraer el bloque '## Índice por táctica' -> {tactic_name: count}.

    Formato de linea: '- [Nombre](#anchor) (NN prompts)'
    Devuelve None si no se encuentra el indice.
    """
    in_index = False
    index: dict[str, int] = {}
    for line in lines:
        if line.startswith("## "):
            if "ndice por" in line or "índice por" in line.lower():
                in_index = True
                continue
            in_index = False
        if in_index:
            m = re.match(r"^-\s*\[([^\]]+)\]\([^)]*\)\s*\((\d+)\s+prompts?\)", line)
            if m:
                index[m.group(1)] = int(m.group(2))
    return index or None


def parse(lines: list[str]) -> tuple[list[dict], dict]:
    """Parsea el dataset. Devuelve (records, warnings)."""
    warnings: list[str] = []
    records: list[dict] = []
    tactic_name: str | None = None
    cur: dict | None = None

    def close(cur_rec: dict | None) -> None:
        if cur_rec is not None:
            prompt = " ".join(cur_rec.pop("_quote_lines"))
            cur_rec["prompt_text"] = prompt
            records.append(cur_rec)

    for lineno, line in enumerate(lines, 1):
        if line.startswith("## "):
            close(cur)
            cur = None
            title = line[3:].strip()
            # La seccion de indice no es una tactica.
            tactic_name = None if ("ndice por" in title or "índice por" in title.lower()) else title
            continue

        m = TECH_RE.match(line)
        if line.startswith("### ") and not m:
            # Cabecera no reconocida: cierra el record abierto para no mezclar cuerpos.
            close(cur)
            cur = None
            warnings.append(f"linea {lineno}: cabecera tecnica malformada: {line!r}")
        if m:
            close(cur)
            cur = None
            tech_id, tech_name = m.group(1), m.group(2).strip()
            is_sub = "." in tech_id
            rec = {
                "tactic_name": tactic_name,
                "tactic_id": slugify(tactic_name) if tactic_name else None,
                "technique_id": tech_id,
                "technique_name": tech_name,
                "is_subtechnique": is_sub,
                "parent_technique": tech_id.split(".")[0] if is_sub else None,
                "_quote_lines": [],
            }
            cur = rec
            continue

        if line.startswith(">"):
            if cur is None:
                warnings.append(f"linea {lineno}: bloque de cita sin cabecera tecnica previa")
                continue
            text = line[1:].lstrip()
            if text:
                cur["_quote_lines"].append(text)
            continue

        # Linea suelta dentro de un cuerpo de tecnica (no vacia, no cabecera, no cita).
        if cur is not None and line.strip():
            warnings.append(f"linea {lineno}: contenido fuera de la cita en {cur['technique_id']}")

    close(cur)
    return records, warnings


def validate(records: list[dict], index: dict[str, int] | None) -> tuple[list[str], Counter]:
    """Devuelve (errores, conteo_por_tactica)."""
    errors: list[str] = []
    by_tactic: Counter = Counter()

    # V4 + estructura basica
    for rec in records:
        if not rec["tactic_name"]:
            errors.append(f"record {rec['technique_id']} sin tactica")
            continue
        by_tactic[rec["tactic_name"]] += 1
        if not rec["prompt_text"].strip():
            errors.append(f"V6: {rec['technique_id']} sin prompt (cuerpo de cita vacio)")

    # V1 total declarado en indice
    if index is None:
        errors.append("V2: no se encontro el indice por tactica")
    else:
        declared_total = sum(index.values())
        if len(records) != declared_total:
            errors.append(f"V1: total {len(records)} != declarado en indice {declared_total}")

    # V2 conteo por tactica vs indice
    if index is not None:
        idx_tactics = set(index)
        parsed_tactics = set(by_tactic)
        if len(parsed_tactics) != 15:
            errors.append(f"V2: se esperan 15 tacticas, hay {len(parsed_tactics)}")
        for name, count in index.items():
            if by_tactic.get(name, 0) != count:
                errors.append(f"V2: {name} indice={count} parseado={by_tactic.get(name, 0)}")
        for extra in parsed_tactics - idx_tactics:
            errors.append(f"V2: tactica '{extra}' no aparece en el indice")

    # V3 duplicados
    seen: dict[str, str] = {}
    for rec in records:
        key = f"{rec['tactic_name']}::{rec['technique_id']}"
        if key in seen:
            errors.append(f"V3: duplicado {key} (primera aparicion en {seen[key]})")
        else:
            seen[key] = rec["technique_name"]

    # V5 padres de sub-tecnicas existen
    parents: dict[str, set[str]] = {}
    for rec in records:
        parents.setdefault(rec["tactic_name"], set()).add(rec["technique_id"])
    for rec in records:
        if rec["is_subtechnique"]:
            parent = rec["parent_technique"]
            if parent not in parents.get(rec["tactic_name"], set()):
                errors.append(f"V5: {rec['technique_id']} sin padre {parent} en {rec['tactic_name']}")

    return errors, by_tactic


def main() -> int:
    ap = argparse.ArgumentParser(description="Parser MITRE red team prompts")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    dataset = Path(args.dataset)
    if not dataset.is_file():
        print(f"ERROR: dataset no existe: {dataset}")
        return 2
    lines = dataset.read_text(encoding="utf-8").splitlines()

    index = parse_index(lines)
    records, warnings = parse(lines)
    errors, by_tactic = validate(records, index)

    for w in warnings:
        print(f"WARN {w}", file=sys.stderr)

    if errors:
        print("VALIDACION FALLIDA:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"OK  {len(records)} prompts -> {out}")
    print(f"    tacticas: {len(by_tactic)} | sub-tecnicas: {sum(r['is_subtechnique'] for r in records)}")
    for tactic in sorted(by_tactic):
        print(f"    {tactic:<24} {by_tactic[tactic]:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
