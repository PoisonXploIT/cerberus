"""Arranca la UI de CERBERUS en loopback (sin depender de scripts locales).

Uso:
    python scripts/ui_serve.py                # 127.0.0.1:8599
    python scripts/ui_serve.py --port 8600

El bind es siempre 127.0.0.1: la UI maneja contenido ofensivo y no debe exponerse.
El token de sesion se genera/lee en `runs/.ui_token`; los scripts lo usan para las
peticiones a /api/*. La primera vez, abre la raiz en el navegador para recibir la
cookie de sesion.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "src", ROOT / "src" / "ui"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

HOST = "127.0.0.1"


def main() -> int:
    ap = argparse.ArgumentParser(description="UI de CERBERUS (solo loopback)")
    ap.add_argument("--port", type=int, default=8599,
                    help="puerto local (1024-65535, por defecto 8599)")
    args = ap.parse_args()
    if not (1024 <= args.port <= 65535):
        print("puerto fuera de rango: usa 1024-65535", file=sys.stderr)
        return 2

    try:
        import uvicorn
    except ImportError:
        print("falta uvicorn: pip install -r requirements.txt", file=sys.stderr)
        return 1

    from security import ui_token  # noqa: E402  (necesita src/ui en sys.path)

    token_path = ROOT / "runs" / ".ui_token"
    ui_token()  # asegura que existe antes de aceptar peticiones
    print(f"CERBERUS UI -> http://{HOST}:{args.port}")
    print(f"token de sesion: {token_path}")
    print("abre la raiz en el navegador para recibir la cookie; Ctrl+C para parar")
    uvicorn.run("ui.main:app", host=HOST, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
