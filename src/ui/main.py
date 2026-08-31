"""CERBERUS UI — FastAPI app (Fase 5a, dashboard offline).

Bind estricto a 127.0.0.1 y sin auth por diseño: el contenido son respuestas
ofensivas reales (comandos, evasión AMSI/ETW, SPL), NUNCA exponer fuera de
localhost. El toggle "sanitizar" va ON por defecto en el frontend.

Arranque:
  ui_serve.bat            (o) .venv/Scripts/python.exe -m uvicorn ui.main:app --host 127.0.0.1 --port 8599
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

# Paquete plano, mismo patron que src/run_mitre_eval.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.compare import router as compare_router  # noqa: E402
from api.runner import router as runner_router  # noqa: E402
from api.stats import router as stats_router  # noqa: E402
from db import recover_orphans  # noqa: E402
from home import reports_dir  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Informes de la carpeta reports/ del home (solo se listan los que existan).
REPORTS = {
    "informe_legible": reports_dir() / "informe_legible.md",
    "informe_tecnico": reports_dir() / "informe_cerberus_875.md",
    "resumen_json": reports_dir() / "resumen_ejecutivo.json",
    "tacticas_csv": reports_dir() / "resumen_tacticas_875.csv",
    "tecnicas_csv": reports_dir() / "resumen_tecnicas_875.csv",
}


def create_app() -> FastAPI:
    # Runs huérfanos de una sesión anterior (la UI se reinició con un run en curso).
    n = recover_orphans()
    if n:
        print(f"aviso: {n} run(s) huérfano(s) marcados como error; reanuda desde checkpoint.")
    app = FastAPI(title="CERBERUS UI", docs_url=None, openapi_url=None)
    app.include_router(stats_router)
    app.include_router(runner_router)
    app.include_router(compare_router)

    @app.get("/api/reports")
    def list_reports():
        return {k: v.name for k, v in REPORTS.items() if v.exists()}

    # Registro ANTES de /api/reports/{name}: FastAPI machaca por orden.
    @app.get("/api/reports/all")
    def download_all_reports():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for v in REPORTS.values():
                if v.exists():
                    z.write(v, arcname=v.name)
        buf.seek(0)
        return Response(
            content=buf.read(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="cerberus_reports.zip"'},
        )

    @app.get("/api/reports/{name}")
    def download_report(name: str):
        if name not in REPORTS:
            raise HTTPException(404, "Reporte no encontrado")
        path = REPORTS[name]
        if not path.exists():
            raise HTTPException(404, "El fichero no existe en disco")
        return FileResponse(path, filename=path.name)
    # Montaje en "/" al final: las rutas /api/* ya registradas tienen prioridad.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import os

    import uvicorn

    print("AVISO: la UI escucha SOLO en 127.0.0.1 y no tiene auth por diseno.")
    print("No expongas este puerto fuera de localhost.")
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("CERBERUS_UI_PORT", "8599")))
