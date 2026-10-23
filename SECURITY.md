# Security Policy

CERBERUS is a **defensive** evaluation framework. It audits local LLMs against
MITRE ATT&CK prompts and scores harmful output. It never executes payloads, and
the repository contains no model weights, API keys or execution results:
datasets and run outputs stay local and are gitignored by design.

The prompt templates describe adversarial scenarios for **authorized** security
research only (red-team exercises with written permission, defensive risk
assessment).

## Modelo de amenazas de la UI

La interfaz es de un solo usuario y escucha en `127.0.0.1:8599`. "Solo localhost"
no basta: un navegador puede hablar con loopback (DNS rebinding), y cualquier
proceso local puede hacer peticiones. Riesgos considerados:

| Riesgo | Mitigación |
|---|---|
| DNS rebinding / Host falso | Se rechaza todo `Host` que no sea `localhost`, `127.0.0.1`, `::1` (o `CERBERUS_ALLOWED_HOSTS`) |
| CSRF desde otra pestaña | Cookie de sesión `HttpOnly; SameSite=Strict` + validación de `Origin` en métodos que cambian estado |
| Acceso de procesos locales | Token de sesión obligatorio en `/api/*` y `/events/*` (cookie o `X-CERBERUS-Token`) |
| SSRF con la key del juez | `base_url` del juez contra allowlist `https`; http solo para loopback de pruebas |
| SSRF al servidor "local" | `local_base_url` limitado a loopback |
| Path traversal por `run_id` | Regex estricta y comprobación de que el destino queda dentro de `runs/` |
| Extracción masiva o DoS | `limit ≤ 1000`, `max_tokens ≤ 16384`, dos jobs concurrentes, timeouts |
| XSS con respuestas del modelo | Frontend pinta con `textContent`; CSP con `script-src 'self'` |
| Fuga por caché del navegador | `Cache-Control: no-store` en `/api/*` |
| Contenido ofensivo accidental | Modo demo y ocultado de bloques de código activados por defecto |

El token se guarda en `runs/.ui_token` (0600, gitignoreado) y se puede fijar con
`CERBERUS_UI_TOKEN`. Los scripts de verificación lo leen de ahí.

## Datos y secretos

- Claves solo por variables de entorno (`JUDGE_API_KEY`, `OPENROUTER_API_KEY`).
- `data/`, `runs/`, `reports/`, `logs/`, `config/*.yaml` y los `.bat` reales están
  fuera del repo (ver `.gitignore`).
- `scripts/sanity_check.py` revisa que no haya nombres reales de modelo ni claves
  en el árbol versionado; la CI lo ejecuta en cada push.
- Los logs no incluyen prompts ni respuestas completas por defecto.

## Alcance y uso

- Uso en laboratorio aislado; el modelo evaluado no tiene red de producción.
- No exponer la UI fuera de loopback. Si hiciera falta acceso remoto, usar túnel
  autenticado (p. ej. Tailscale) además del token, nunca un puerto abierto.
- Contenido generado: respuestas ofensivas reales. Trátalo como material sensible.

## Reportar una vulnerabilidad

Abre un **security advisory privado** en GitHub en lugar de un issue público, con
pasos de reproducción y versión (commit) afectada.
