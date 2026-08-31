"""CERBERUS Fase 3: configuracion central (pydantic-settings).

Regla de seguridad (acta 5): las keys SOLO por variables de entorno,
nunca en codigo ni en ficheros.

Variables de entorno (sin prefijo):
  LOCAL_BASE_URL   default http://localhost:8085/v1
  LOCAL_TIMEOUT_S  timeout por peticion al local (default 600; respuestas largas)
  JUDGE_BASE_URL   base URL OpenAI-compatible del juez (default OpenRouter)
  JUDGE_API_KEY    key del proveedor del juez (fallback: OPENROUTER_API_KEY)
  JUDGE_MODEL      modelo del juez (solo modo activo / casos ambiguos)
"""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Local (objetivo bajo test: modelo local via llama.cpp, servidor a mano)
    local_base_url: str = "http://localhost:8085/v1"
    local_model: str = "local"          # llama.cpp sirve el id del .bat; 'local' funciona como placeholder
    local_timeout_s: float = 600.0

    # Juez (solo modo activo o casos ambiguos; CERO uso en modo pasivo)
    judge_base_url: str = "https://openrouter.ai/api/v1"
    judge_api_key: str | None = None    # env JUDGE_API_KEY u OPENROUTER_API_KEY
    judge_model: str | None = None      # p.ej. deepseek/deepseek-chat-v3, openai/gpt-4o-mini...
    judge_timeout_s: float = 120.0

    # Pipeline
    checkpoint_every: int = 10


def load_settings() -> Settings:
    """Carga settings con fallback de la key del juez (OpenRouter)."""
    s = Settings()
    if not s.judge_api_key:
        s.judge_api_key = os.environ.get("OPENROUTER_API_KEY")
    return s
