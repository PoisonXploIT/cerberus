# CERBERUS — Evaluación defensiva de LLMs locales ante prompts adversarios

> *Defensive evaluation framework for auditing local LLMs against adversarial
> prompts structured with MITRE ATT&CK. It helps security teams measure
> harmful-output risk before deploying uncensored models in internal
> environments.*

Framework reutilizable de **evaluación defensiva y safety research**: mide el
riesgo de salida accionable de un modelo local ante prompts adversariales
estructurados con MITRE ATT&CK, para que los equipos de seguridad evalúen ese
riesgo antes de desplegar modelos sin censura en entornos internos.
Puntuación determinista + juez LLM cloud opcional en la banda ambigua.

> **Uso autorizado:** esta herramienta está pensada para investigación de
> seguridad autorizada, ejercicios red team con permiso por escrito y assessment
> de riesgo defensivo. El usuario es responsable de cumplir la legislación y las
> políticas aplicables a su contexto.

**Pasivo y reportable:** el pipeline es pasivo (prompt → texto). No se ejecuta
ningún payload ni ataque real; el modelo local corre aislado, sin red de
producción.

## Arquitectura

```
[Orquestador Python]  (un solo proceso, INASISTIDO: no depende de pi ni de nube)
  ├─ local_client ──► http://localhost:<puerto>/v1/chat/completions   (modelo local vía llama.cpp; puerto configurable, por defecto 8085)
  └─ judge_client ──► OpenAI-compatible configurable                 (OpenRouter por defecto;
                                                               DeepSeek / Alibaba / OpenAI vía base_url)

Flujo pasivo:  mitre_prompts.jsonl → prompt tal cual → local → heurística → JSONL
Flujo juez:   canónico → banda ambigua [0.3, 0.7) → judge cloud (JSON estricto)
              → merge conservador harm_final = max(heurística, juez)  (el juez solo sube)
```

- Un solo cliente HTTP OpenAI-compatible para ambos roles (`src/clients.py`).
- Puntuación en dos capas: heurística determinista primero; LLM-judge solo la
  banda ambigua o modo activo.
- Modo pasivo por defecto: CERO llamadas cloud en el envío del prompt.
- Checkpoint por registro, reanudación por `--run-id`, hash SHA-256 de cada respuesta.

### Restricción GPU (crítica)

El modelo objetivo suele ocupar la GPU completa; cargarlo peta con el proceso que
corre pi. Por eso el batch es **inasistido**: un solo proceso Python sin inferencia
de pi ni cloud en modo pasivo. El servidor llama.cpp se arranca a mano con su `.bat`
— el pipeline NUNCA lo carga. Si el puerto no responde, el CLI aborta limpio (exit 2)
o sondea hasta 30 min (`wait_for_server`) para que el watchdog re-arranque.

## Estructura

```
CERBERUS/
├─ README.md / PLAN.md
├─ data/                        # dataset parseado + results_*.jsonl (gitignored)
├─ runs/                        # un directorio por run: results.jsonl + summary (gitignored)
├─ reports/                     # informes generados MD/PDF/JSON/CSV (gitignored)
├─ logs/                        # logs de servidor/UI (gitignored)
├─ config/                      # settings opcionales (los reales gitignored; keys SOLO por env)
├─ src/
│  ├─ parser_mitre.py           # Markdown → JSONL (gate: exit != 0 si falla)
│  ├─ fix_dataset_v192.py       # corrección STIX v19.2 (idempotente)
│  ├─ run_mitre_eval.py         # CLI + pipeline reutilizable (pasivo/juez)
│  ├─ select_ambiguous.py       # canónico → banda ambigua
│  ├─ merge_judge.py            # merge conservador harm_final
│  ├─ validate_judge.py         # muestreo para auditoría humana
│  ├─ generate_report.py        # informe + CSV (--source merged)
│  ├─ export_deliverables.py    # informe legible MD/PDF + JSON + CSV técnicas
│  ├─ clients.py / config.py    # cliente único HTTP + settings (keys solo por env)
│  └─ ui/                       # FastAPI + HTML/JS vanilla, bind 127.0.0.1:8599
├─ scripts/sanity_check.py      # verificación pre-push: sin datos reales en el repo
├─ server_repeatpenalty.bat.example   # plantilla servidor (re-runs; rellenar rutas)
├─ server_watchdog.bat.example        # plantilla watchdog (re-arranque si cae)
├─ watchdog_repeatpenalty.bat.example # plantilla watchdog del re-run
└─ .venv/                       # Python 3.12, requests/pydantic/fastapi/uvicorn
```

Los `.bat` reales (con rutas y modelo propios) son locales y gitignored: copia las
plantillas `*.bat.example`, rellena `MODEL_PATH` / `LLAMA_SERVER` y usa el nombre sin
`.example`.

## Instalación

Requisitos: Python 3.12 (Windows, macOS o Linux). Para evaluar un modelo hace falta
ademas llama.cpp y una GPU con VRAM suficiente para el offload completo; la UI y los
tests funcionan sin GPU y sin datos.

```bat
git clone https://github.com/PoisonXploIT/cerberus.git
cd cerberus
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

En macOS/Linux: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

El servidor del modelo objetivo se arranca **a mano** con tu `.bat` (copia una de
las plantillas `server_*.bat.example`) en un puerto configurable — por defecto 8085,
solo localhost. Verificación: `GET http://localhost:8085/v1/models`.

## Uso

### Parser (dataset)

```bat
.venv\Scripts\python.exe src\parser_mitre.py
```

Lee el dataset MITRE (ruta configurable en el script), valida (tácticas, sin
duplicados, subs asociadas a padre) y escribe `data/mitre_prompts.jsonl`. Si falla
la validación: `exit != 0`.

### Batch pasivo (inasistido)

```bat
.venv\Scripts\python.exe src\run_mitre_eval.py --tactic persistence --limit 5   # prueba
.venv\Scripts\python.exe src\run_mitre_eval.py                                  # batch completo
```

Flags relevantes: `--temperature`, `--max-tokens`, `--repeat-penalty` (usar **1.15**
para evitar el colapso repetitivo), `--rerun-from <results.jsonl>` + `--harm-below`
para re-ejecutar subconjuntos, `--run-id` para reanudar desde checkpoint.

### Juez (banda ambigua)

```bat
set OPENROUTER_API_KEY=...                      :: key SOLO por env, nunca en código
.venv\Scripts\python.exe src\select_ambiguous.py
.venv\Scripts\python.exe src\run_mitre_eval.py --mode judge --judge-input data\ambiguous.jsonl
.venv\Scripts\python.exe src\merge_judge.py    :: harm_final = max(heurística, juez)
.venv\Scripts\python.exe src\validate_judge.py :: muestreo → data/validation_sample.md
```

Sin key: abort limpio exit 2 (el merge sin juez documenta harm_final = heurística).

### Informes, exports y UI

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt      :: dependencias pinneadas
.venv\Scripts\python.exe src\generate_report.py --source merged   :: informe técnico + CSV tácticas
.venv\Scripts\python.exe src\export_deliverables.py              :: informe legible MD/PDF + JSON + CSV técnicas
.venv\Scripts\python scripts\ui_serve.py                          :: http://127.0.0.1:8599
```

El nombre del modelo que aparece en los entregables se toma de la variable de
entorno `LOCAL_MODEL_NAME` (fallback: «modelo local evaluado»); el código genérico
nunca lleva el nombre real.

UI: dashboard offline sobre el results canónico de `data/` (prioridad: nombre con
"canonical", desempate por mtime) + runner online (SSE, cancelar/reanudar desde
checkpoint, SQLite en `runs/runs.sqlite3`). Sin datos: el dashboard muestra estado
`no_data` hasta que exista un results.

Arranque de la UI: `python scripts/ui_serve.py` (o copia `ui_serve.example.bat`).
Escucha solo en `127.0.0.1:8599` y exige token de sesion: se genera en
`runs/.ui_token` y se entrega como cookie al abrir la raiz en el navegador. Los
scripts lo leen de ese fichero para `/api/*`.

La interfaz (`src/ui/static/`) es HTML + CSS + JS sin dependencias ni CDN:
navegación lateral, estado del servidor local, tabla ordenable y navegable por
teclado, detalle en panel lateral con pestañas (prompt / respuesta / métricas) y
foco atrapado, historial de runs con acciones (ver, juzgar, reanudar, borrar),
confirmación en acciones destructivas, informes con tamaño y fecha y exportación
CSV de la comparativa. Tema oscuro y claro; icono de las tres cabezas y favicon
propios.

Endpoints de la UI: `/api/stats`, `/api/results[/{i}]`, `/api/runs`, `/api/history`,
`/api/run` (POST), `/api/run/{id}/cancel|resume|judge`, `DELETE /api/run/{id}`,
`/api/local/status`, `/api/config/judge`, `/api/reports[/info|/all|/{key}]` y
`/events/run/{id}` (SSE).

## Sitio publico de resultados (opcional)

`src/publish_site.py` publica **solo agregados** de un run en un repo privado
(`cerberus-site`) y despliega en Cloudflare Pages bajo `cerberus.sammideblas.com`,
protegido con Cloudflare Access.

```bat
copy config\publish.example.json config\publish.json   :: ajusta site_repo
.venv\Scripts\python.exe src\publish_site.py --dry-run
.venv\Scripts\python.exe src\publish_site.py --yes
.venv\Scripts\python.exe src\publish_site.py --setup  :: Pages + dominio + DNS + Access
```

- El payload se **audita** antes de escribir: sin prompts, respuestas, rutas, IPs,
  URLs, tokens ni cadenas largas. Si la auditoria falla, no se escribe nada.
- No acepta URLs: repo, proyecto y dominio vienen de `config/publish.json` o del
  entorno, y se validan (proyecto `^[a-z0-9-]+$`; dominio subdominio de
  `sammideblas.com`).
- El token de Cloudflare se lee del entorno o del registro de Windows y se pasa a
  wrangler; nunca se escribe en el repo.
- Mismo flujo desde la UI local: seccion **Publicar** con previsualizacion y boton,
  endpoint `POST /api/publish` (token de sesion, `confirm` obligatorio, un solo job).

El sitio (`cerberus-site`) es estatico: HTML, CSS y JS propios, `data.json` con los
agregados y `_headers` con CSP estricta, `noindex` y sin framing.

## Seguridad

- Keys solo por variables de entorno; nunca en código ni logs.
- Puerto del servidor configurable (por defecto 8085) solo loopback; UI bind estricto
  a `127.0.0.1:8599`.
- **Token de sesión local**: la UI genera `runs/.ui_token` (0600) al arrancar y lo
  entrega como cookie `HttpOnly; SameSite=Strict` al abrir `/`. Las rutas `/api/*` y
  `/events/*` exigen ese token (cookie o cabecera `X-CERBERUS-Token`). Los scripts de
  prueba lo leen del fichero.
- **Anti-DNS-rebinding**: se rechaza cualquier `Host` que no sea loopback, y los
  métodos que cambian estado con `Origin` externo.
- **Allowlist de URLs**: el servidor local debe ser loopback; el juez solo `https`
  contra `JUDGE_ALLOWED_HOSTS` (por defecto OpenRouter, DeepSeek, OpenAI, Anthropic,
  DashScope). La API key nunca se manda a un host fuera de la lista.
- **Validación de `run_id`** en todas las entradas: sin `..`, sin separadores; nada
  escribe fuera de `runs/`.
- **Límites**: `limit ≤ 1000`, `max_tokens ≤ 16384`, dos jobs concurrentes como máximo
  (un run y un juez).
- Cabeceras `Content-Security-Policy` (script-src estricto), `nosniff`,
  `no-referrer`, `frame-ancestors none` y `Cache-Control: no-store` en `/api/*`.
- **Sanitizado por defecto** en el detalle: oculta bloques de código, comandos
  inline, IPs, hashes, dominios y blobs largos (best-effort para demos, no es una
  garantía).
- Logs sin prompts ni respuestas: `logs/ui.log` con rotación (1 MB x 3) registra
  arranque, runs, borrados y errores por `run_id`.
- Modelo local aislado: sin red de producción, sin sistemas reales, sin ejecución de
  payloads.

Detalle del modelo de amenazas en `SECURITY.md`.

## Verificación pre-push

```bat
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python tests\check_http_security.py   :: con la UI levantada
.venv\Scripts\python scripts\sanity_check.py       :: debe devolver 0
```

`unittest` cubre validación de `run_id`, allowlist de URLs y comprobaciones de `Host`.
`check_http_security.py` verifica en vivo token, cabeceras, traversal, SSRF,
historial y borrado.
`sanity_check.py` comprueba que no haya nombres reales de modelo ni keys en el árbol.
CI (`.github/workflows/ci.yml`) ejecuta compilación, tests y `sanity_check` en cada
push.

## Fase II — trabajo futuro (NO APROBADO; plan y aprobación propios)

1. **Modo activo**: reformular prompts con el orquestador cloud y medir si el local
   cede más. Primer paso obligatorio: estimación de tokens/coste antes de gastar un
   token; subconjunto 50-100 prompts de alto riesgo, no el batch completo;
   presupuesto controlado.
2. **Multi-modelo**: reutilizar el pipeline para evaluar otros LLM locales
   candidatos (dataset congelado con fingerprint, `--run-id` por modelo,
   juez/merge reutilizables).
3. **Exportar UI a PDF**: «descargar informe» desde el dashboard.

Plan de trabajo: `PLAN.md`.

---

## Contacto

- Pagina: [sammideblas.com](https://sammideblas.com)
- Email: analista@sammideblas.com
