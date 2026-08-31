"""CERBERUS Fase 3: cliente HTTP OpenAI-compatible unico (acta 1).

Un solo cliente para los dos roles:
  local_client -> http://localhost:8085/v1/chat/completions  (modelo local)
  judge_client -> base URL configurable (OpenRouter por defecto; DeepSeek/Alibaba/OpenAI intercambiables)

El endpoint legacy /completion queda descartado. El pipeline NUNCA carga el
modelo: si el servidor no responde, se aborta limpiamente (el servidor se
arranca a mano con su .bat).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from config import Settings, load_settings


class ServerDown(RuntimeError):
    """El servidor llama.cpp no responde. Abortar: NUNCA cargar el modelo desde el pipeline."""


class ClientError(RuntimeError):
    """Error de peticion HTTP ya enviada (HTTP >= 400, timeout, JSON roto)."""


@dataclass
class ChatResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    finish_reason: str | None = None
    raw: dict = field(default_factory=dict)


class OpenAICompatClient:
    """Cliente minimo a POST /chat/completions (requests, sin dependencias extra)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout_s: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        # El local no necesita key real; el juez si (solo env).
        self.api_key = api_key

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 2048,
        extra: dict | None = None,
    ) -> ChatResult:
        """Una peticion de chat. Lanza ServerDown/ClientError; el orquestador decide reintentos."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if extra:
            payload.update(extra)

        url = f"{self.base_url}/chat/completions"
        t0 = time.perf_counter()
        try:
            r = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout_s)
        except requests.exceptions.ConnectError as e:
            raise ServerDown(f"sin conexion en {url} (servidor a mano con su .bat)") from e
        except requests.exceptions.Timeout as e:
            raise ClientError(f"timeout tras {self.timeout_s}s en {url}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code >= 400:
            raise ClientError(f"HTTP {r.status_code} de {url}: {r.text[:300]}")

        try:
            data = r.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            usage = data.get("usage", {})
            return ChatResult(
                text=text,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                finish_reason=choice.get("finish_reason"),
                raw=data,
            )
        except (KeyError, IndexError, ValueError) as e:
            raise ClientError(f"respuesta no parseable de {url}: {e}") from e

    def ping(self) -> list[str]:
        """GET /models para verificar el servidor. Solo lectura; nunca carga nada."""
        try:
            r = requests.get(f"{self.base_url}/models", timeout=5, headers=self._headers())
            if r.status_code >= 400:
                raise ServerDown(f"HTTP {r.status_code} en GET {self.base_url}/models")
            return [m["id"] for m in r.json().get("data", [])]
        except requests.exceptions.RequestException as e:
            raise ServerDown(f"sin respuesta en {self.base_url}/models ({e})") from e


def build_clients(settings: Settings | None = None) -> tuple[OpenAICompatClient, OpenAICompatClient]:
    """Devuelve (local_client, judge_client). El juez puede no estar configurado
    (modo pasivo puro); en ese caso se construye igualmente y solo falla si se usa."""
    s = settings or load_settings()
    local = OpenAICompatClient(s.local_base_url, s.local_model, timeout_s=s.local_timeout_s)
    judge = OpenAICompatClient(
        s.judge_base_url,
        s.judge_model or "unconfigured",
        api_key=s.judge_api_key,
        timeout_s=s.judge_timeout_s,
    )
    return local, judge
