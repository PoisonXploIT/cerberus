"""Comprobaciones HTTP de seguridad contra la UI en marcha (sin dependencias).

Uso (con la UI levantada en 127.0.0.1:8599):

    .venv\\Scripts\\python.exe tests\\check_http_security.py

No manda trafico a Internet: todo va a loopback; las URLs "malas" solo aparecen
en el cuerpo JSON para verificar que el servidor las rechaza antes de usarlas.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8599"
ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / "runs" / ".ui_token"
RID = "run_20260830_010330"

fallos = 0


def call(path: str, method: str = "GET", body=None, token: bool = True,
         host: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token and TOKEN_FILE.exists():
        req.add_header("X-CERBERUS-Token", TOKEN_FILE.read_text(encoding="utf-8").strip())
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(name: str, got, want) -> None:
    global fallos
    ok = got == want if not isinstance(want, (list, tuple)) else got in want
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {got} (esperado {want})")
    if not ok:
        fallos += 1


def main() -> int:
    st, headers, _ = call("/", token=False)
    check("GET / publico", st, 200)
    check("CSP presente", bool(headers.get("content-security-policy")), True)
    check("cookie de sesion", "cerberus_ui=" in (headers.get("set-cookie") or ""), True)

    check("API sin token", call("/api/stats", token=False)[0], 401)
    check("API con token", call("/api/stats")[0], 200)
    check("Cache-Control no-store",
          (call("/api/stats")[1].get("cache-control") or "").lower(), "no-store")

    check("Host no local", call("/api/health", token=False, host="rebind.example")[0], 403)

    check("run_id traversal",
          call("/api/run", "POST", {"run_id": "../../poc", "limit": 1})[0], 422)
    check("local_base_url remota",
          call("/api/run", "POST", {"limit": 1, "local_base_url": "http://10.9.9.9:8085/v1"})[0], 422)
    check("juez base_url remota",
          call(f"/api/run/{RID}/judge", "POST", {"base_url": "http://10.9.9.9:8085/v1"})[0], 422)
    check("juez http no loopback",
          call(f"/api/run/{RID}/judge", "POST", {"base_url": "http://api.openai.com/v1"})[0], 422)
    check("limite fuera de rango",
          call("/api/run", "POST", {"limit": 999999})[0], 422)
    check("max_tokens fuera de rango",
          call("/api/run", "POST", {"max_tokens": 999999})[0], 422)

    check("reports/info", call("/api/reports/info")[0], 200)
    check("events sin token", call(f"/events/run/{RID}", token=False)[0], 401)
    check("history", call("/api/history")[0], 200)
    check("publish sin token", call("/api/publish", "POST", {"dry_run": True}, token=False)[0], 401)
    check("publish run invalido",
          call("/api/publish", "POST", {"run_id": "../x", "dry_run": True})[0], 422)
    check("publish sin confirmar",
          call("/api/publish", "POST", {"dry_run": False})[0], (428, 409, 422))
    check("publish dry-run",
          call("/api/publish", "POST", {"dry_run": True})[0], (200, 409))
    check("borrar run inexistente", call("/api/run/no_existe_123", "DELETE")[0], 404)
    check("borrar run_id invalido", call("/api/run/..%2Fescape", "DELETE")[0], (400, 404, 405))

    print("\nRESULTADO:", "OK" if fallos == 0 else f"{fallos} fallos")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
