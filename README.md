# CERBERUS — Cyber Evaluation & Red-teaming Benchmark for Uncensored Systems

Framework reutilizable para evaluar LLM locales: mide qué tanto un modelo local
genera contenido accionable de red team a partir de prompts MITRE ATT&CK, con
puntuación determinista + juez LLM cloud opcional en la banda ambigua.

**Uso defensivo y reportable:** el pipeline es pasivo (prompt → texto). No se
ejecuta ningún payload ni ataque real. El modelo local corre aislado, sin red de
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

Requisitos: Windows, Python 3.12, GPU compatible con CUDA con VRAM suficiente para
offload completo, llama.cpp.

```bat
py -3.12 -m venv .venv
.venv\Scripts\pip install requests pydantic pydantic-settings fastapi uvicorn fpdf2
```

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
.venv\Scripts\python.exe src\generate_report.py --source merged   :: informe técnico + CSV tácticas
.venv\Scripts\python.exe src\export_deliverables.py              :: informe legible MD/PDF + JSON + CSV técnicas
ui_serve.bat                                                      :: http://127.0.0.1:8599
```

El nombre del modelo que aparece en los entregables se toma de la variable de
entorno `LOCAL_MODEL_NAME` (fallback: «modelo local evaluado»); el código genérico
nunca lleva el nombre real.

UI: dashboard offline sobre el results canónico de `data/` (prioridad: nombre con
"canonical", desempate por mtime; cards,
buckets, gráfico SVG por táctica, tabla filtrable con vista detalle y sanitizador ON
por defecto) + runner online (SSE, cancelar/reanudar desde checkpoint, SQLite en
`runs/runs.sqlite3`). Sin datos: el dashboard muestra estado `no_data` hasta que
exista un results.

## Seguridad

- Keys solo por variables de entorno; nunca en código ni logs.
- Puerto del servidor configurable (por defecto 8085) solo localhost; UI bind
  estricto a `127.0.0.1:8599` (sin auth: no exponer).
- Logs sin prompts completos por defecto (debug opt-in); llama.cpp con logs saneados.
- Modelo local aislado: sin red de producción, sin sistemas reales, sin ejecución de
  payloads.

## Verificación pre-push

```bat
.venv\Scripts\python scripts\sanity_check.py
```

Debe devolver **0** antes de cada push: comprueba que ningún fichero del repo
contenga nombres reales de modelo ni keys hardcodeadas.

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
