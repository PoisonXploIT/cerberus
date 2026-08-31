"""CERBERUS — E2E con servidores fake (sin GPU ni nube).

Requiere:
  - UI corriendo en 127.0.0.1:8599 CON JUDGE_API_KEY dummy en su env
  - tests/fake_openai_server.py en 8191 (texto powershell -> harm 0.35)
  - tests/fake_openai_server.py en 8192 --judge (JSON fake harm 0.82)
  - tests/fake_openai_server.py en 8193 con texto de rechazo

Verifica: URL configurable, juez end-to-end, merged conservador, compare, zip.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "http://127.0.0.1:8599"
RUNS = Path(r"C:\Users\Sammi\CERBERUS\runs")


def req(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_status(run_id: str, want: str = "completed", timeout: float = 90.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, rows = req("GET", "/api/runs")
        for r in rows:
            if r["run_id"] == run_id and r["status"] == want:
                return True
        time.sleep(2)
    return False


def wait_file(path: Path, lines: int, timeout: float = 90.0) -> int:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if path.exists():
            n = sum(1 for l in path.open(encoding="utf-8") if l.strip())
            if n >= lines:
                return n
        time.sleep(2)
    return 0


ok = True


def check(name: str, cond) -> None:
    global ok
    print(("OK   " if cond else "FALLO"), name)
    ok = ok and bool(cond)


# 1. Run A contra 8191 (URL configurable; texto con powershell -> harm 0.35)
st, d = req("POST", "/api/run", {"limit": 2, "max_tokens": 64,
                                  "local_base_url": "http://127.0.0.1:8191/v1"})
check("run A lanzado con URL configurable", st == 200 and "run_id" in d)
ra = d["run_id"]
check("run A completado", wait_status(ra))
rowsA = [json.loads(l) for l in (RUNS / ra / "results.jsonl").open(encoding="utf-8")]
check("run A: 2 filas, estado success, harm 0.35",
      len(rowsA) == 2 and all(r["estado"] == "success" and r["metricas"]["harm_score"] == 0.35
                              for r in rowsA))

# 2. Juez contra 8192 (JSON fake harm 0.82) sobre los 2 casos ambiguos
st, d = req("POST", f"/api/run/{ra}/judge",
            {"base_url": "http://127.0.0.1:8192/v1", "model": "fake-judge"})
check("juez lanzado (200)", st == 200)
n = wait_file(RUNS / ra / "judge.jsonl", 2)
check("judge.jsonl con 2 filas", n == 2)
merged = [json.loads(l) for l in (RUNS / ra / "results_merged.jsonl").open(encoding="utf-8")]
check("merged: heur 0.35 / juez 0.82 / final 0.82 (regla conservadora)",
      len(merged) == 2 and all(
          m["metricas"]["harm_heuristic"] == 0.35
          and m["metricas"]["harm_judge"] == 0.82
          and m["metricas"]["harm_final"] == 0.82 for m in merged))

# 3. Run B contra 8193 (texto de rechazo -> harm ~0)
st, d = req("POST", "/api/run", {"limit": 2, "max_tokens": 64,
                                  "local_base_url": "http://127.0.0.1:8193/v1"})
check("run B lanzado", st == 200)
rb = d["run_id"]
check("run B completado", wait_status(rb))

# 4. Compare A vs B y A vs run CLI (solo en disco, no en la BD de la UI)
st, cmp_ = req("GET", f"/api/runs/{ra}/compare/{rb}")
check("compare A/B responde 200", st == 200)
check("compare: medias distintas y per_tactic poblado",
      abs(cmp_["a"]["harm_heuristic"]["mean"] - cmp_["b"]["harm_heuristic"]["mean"]) > 0.1
      and len(cmp_["per_tactic"]) > 0)
check("compare: A marcado con juez", cmp_["a"]["has_judge"] and not cmp_["b"]["has_judge"])
pt = cmp_["per_technique"]
check("compare: per_technique no vacio, con a_harm/b_harm/diff y ordenado por |diff|",
      len(pt) > 0
      and all(set(r) >= {"tactic", "technique", "a_harm", "b_harm", "diff"} for r in pt)
      and all(abs((pt[i]["diff"] or 0)) >= abs((pt[i + 1]["diff"] or 0))
             for i in range(len(pt) - 1)))
st2, cmp2 = req("GET", f"/api/runs/{ra}/compare/run_20260830_010330")
check("compare contra run CLI (solo en disco)", st2 == 200 and cmp2["b"]["total"] > 0)

# 5. ZIP de reportes
with urllib.request.urlopen(BASE + "/api/reports/all") as resp:
    z = zipfile.ZipFile(io.BytesIO(resp.read()))
names = sorted(z.namelist())
check("zip con los 5 reportes", names == sorted([
    "informe_legible.md", "informe_cerberus_875.md", "resumen_ejecutivo.json",
    "resumen_tacticas_875.csv", "resumen_tecnicas_875.csv"]))

print("RESULTADO:", "TODO OK" if ok else "FALLOS")
sys.exit(0 if ok else 1)
