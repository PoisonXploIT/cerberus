"""CERBERUS UI — auth de sesion local, anti-DNS-rebinding y cabeceras.

Modelo: la UI es de un solo usuario y vive en loopback, pero "solo localhost" no
basta (DNS rebinding, procesos locales, otras pestanas). Defensas:

  1. `Host` debe ser local (bloquea rebinding: el navegador conserva el Host
     del atacante).
  2. Las rutas /api/* exigen un token de sesion (cookie HttpOnly SameSite=Strict
     o cabecera `X-CERBERUS-Token`). El token se genera al arrancar y se guarda
     en `runs/.ui_token` (0600) para que los scripts de prueba puedan leerlo.
  3. Los metodos que cambian estado con `Origin` externo se rechazan.
  4. Cabeceras: CSP con script-src estricto (sin inline), nosniff, no-referrer,
     frame-ancestors none y `Cache-Control: no-store` en /api/* (las respuestas
     son contenido ofensivo). `style-src` admite inline porque las barras de
     progreso fijan su ancho por JS; no hay HTML de terceros ni scripts inline.
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from home import runs_dir

COOKIE = "cerberus_ui"
HEADER = "X-CERBERUS-Token"
EXEMPT = {"/api/health"}
DEFAULT_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

_TOKEN: str | None = None


def allowed_hosts() -> set[str]:
    extra = os.environ.get("CERBERUS_ALLOWED_HOSTS", "")
    return DEFAULT_HOSTS | {h.strip().lower() for h in extra.split(",") if h.strip()}


def ui_token() -> str:
    """Token de sesion: env, o fichero persistente, o uno nuevo."""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    env = os.environ.get("CERBERUS_UI_TOKEN", "").strip()
    if env:
        _TOKEN = env
        return _TOKEN
    path = runs_dir() / ".ui_token"
    if path.exists():
        _TOKEN = path.read_text(encoding="utf-8").strip()
    if not _TOKEN:
        _TOKEN = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TOKEN, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return _TOKEN


def _host_ok(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 con corchetes
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in allowed_hosts()


def _origin_ok(origin: str | None) -> bool:
    if not origin:
        return True  # peticiones same-origin pueden no mandarlo
    from urllib.parse import urlsplit

    return _host_ok(urlsplit(origin).netloc or "")


def _presented_token(request: Request) -> str:
    return (request.headers.get(HEADER) or request.cookies.get(COOKIE) or "").strip()


def _needs_token(path: str) -> bool:
    return path.startswith(("/api/", "/events/")) and path not in EXEMPT


def install(app) -> None:
    """Registra el middleware en la app FastAPI."""
    token = ui_token()

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if not _host_ok(request.headers.get("host")):
            return JSONResponse(
                {"detail": "Host no permitido: la UI solo responde en loopback"},
                status_code=403,
            )
        if not _origin_ok(request.headers.get("origin")):
            return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        if _needs_token(request.url.path):
            if not hmac.compare_digest(_presented_token(request), token):
                return JSONResponse(
                    {"detail": "Falta el token de sesion: recarga / en el navegador "
                               "o manda la cabecera X-CERBERUS-Token"},
                    status_code=401,
                )

        response = await call_next(request)

        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            # HTML, JS y CSS se revalidan siempre (ETag): evita mezclar versiones
            # de app.js e index.html desde la cache del navegador.
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        if request.url.path == "/" and request.method == "GET":
            response.set_cookie(
                COOKIE, token, httponly=True, samesite="strict", path="/"
            )
        return response
