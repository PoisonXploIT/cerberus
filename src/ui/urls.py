"""CERBERUS UI — validacion de URLs configurables.

Dos URLs llegan desde la UI y son peligrosas si se aceptan a ciegas:

  * `local_base_url`  -> el pipeline le manda prompts; solo puede ser loopback.
  * `judge_base_url`  -> el cliente le adjunta `Authorization: Bearer JUDGE_API_KEY`;
                         si apunta fuera de la allowlist, la key se filtra.

Ambas se normalizan aqui; los endpoints devuelven 422 si no pasan.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
DEFAULT_JUDGE_HOSTS = {"openrouter.ai", "api.deepseek.com", "api.openai.com",
                       "api.anthropic.com", "dashscope.aliyuncs.com"}


class BadUrl(ValueError):
    """URL no permitida por la politica de red de la UI."""


def _parts(url: str):
    raw = (url or "").strip()
    if not raw:
        raise BadUrl("URL vacia")
    if any(c in raw for c in ("\n", "\r", "\t", " ")):
        raise BadUrl("la URL contiene espacios o saltos de linea")
    p = urlsplit(raw)
    if not p.scheme or not p.hostname:
        raise BadUrl(f"URL incompleta: {raw!r}")
    if p.username or p.password:
        raise BadUrl("no se permiten credenciales en la URL")
    if p.query or p.fragment:
        raise BadUrl("no se permiten query ni fragmento en la URL base")
    return p


def _is_local(host: str) -> bool:
    h = (host or "").strip("[]").lower()
    if h in LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback


def validate_local_base_url(url: str) -> str:
    """Solo loopback por http (llama.cpp local)."""
    p = _parts(url)
    if p.scheme not in ("http", "https"):
        raise BadUrl("el servidor local debe ser http(s)")
    if not _is_local(p.hostname):
        raise BadUrl(f"el servidor local debe ser loopback, no {p.hostname!r}")
    port = p.port or (443 if p.scheme == "https" else 80)
    if not (1024 <= port <= 65535):
        raise BadUrl(f"puerto no permitido: {port}")
    return url.strip().rstrip("/")


def judge_allowed_hosts() -> set[str]:
    extra = os.environ.get("JUDGE_ALLOWED_HOSTS", "")
    hosts = set(DEFAULT_JUDGE_HOSTS)
    hosts |= {h.strip().lower() for h in extra.split(",") if h.strip()}
    return hosts


def validate_judge_base_url(url: str) -> str:
    """https contra la allowlist; http solo para loopback (fake judge de tests)."""
    p = _parts(url)
    host = (p.hostname or "").lower()
    if p.scheme == "http":
        if not _is_local(host):
            raise BadUrl("el juez debe usar https (solo loopback admite http)")
    elif p.scheme != "https":
        raise BadUrl("el juez debe usar https")
    if not _is_local(host) and host not in judge_allowed_hosts():
        raise BadUrl(
            f"host del juez no permitido: {host!r}. "
            "Añadelo a JUDGE_ALLOWED_HOSTS si es tu proveedor."
        )
    return url.strip().rstrip("/")
