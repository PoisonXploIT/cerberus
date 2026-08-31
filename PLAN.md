# CERBERUS — Plan de trabajo (ajustado)

Orquestador MITRE ATT&CK para evaluación de LLM local.
Nombre completo: CERBERUS — Cyber Evaluation & Red-teaming Benchmark for Uncensored Systems.

## Principios de diseño

- Aislamiento total: el modelo local corre sin acceso a red de producción ni sistemas reales.
- Doble LLM: orquestador en la nube (el "capaz") decide estrategia y puntúa; el modelo local (llama.cpp) es el objetivo bajo test.
- Pipeline reproducible: trazado completo, checkpoints, reanudación.
- Métricas por táctica/técnica para estadísticas e informes.
- Uso defensivo y reportable: documentar comportamientos, no ejecutar ataques. Sin ejecución real de payloads.

## Arquitectura (ajustada)

```
[Orquestador Python]
  ├─ local_client ──► http://localhost:8085/v1/chat/completions  (modelo local, servidor a mano con .bat; puerto configurable, por defecto 8085)
  └─ judge_client ──► OpenAI-compatible configurable (OpenRouter por defecto; DeepSeek/Alibaba/OpenAI vía base_url)

Un solo cliente HTTP para ambos roles. Dataset: mitre_redteam_prompts.md → parser → JSONL/SQLite.
```

- Puntuación en dos capas: heurística determinista primero (comandos shell cmd.exe/powershell -enc/bash -c, IOCs IPs/dominios/hashes/rutas, evasión amsi/etw/disable defender/bypass/obfusc, secciones objetivo/prerrequisitos/ejecución/telemetría/SPL/mitigación) + LLM-judge solo casos ambiguos o modo activo.
- Modo pasivo (default): prompt tal cual, cero nube en el envío. Modo activo: reformulación solo subconjunto calibrado o prompts rechazados. Script de estimación de tokens/coste antes de run activo.
- Batch INASISTIDO por restricción GPU: un proceso Python corre N prompts sin depender de inferencia de pi ni de la nube (modo pasivo). El modelo bajo test ocupa la GPU completa (CUDA); arrancarlo desde otro proceso peta la GPU donde corre pi.
- Seguridad día 1: keys solo env; llama.cpp --log-disable o logs saneados; el puerto del servidor (por defecto 8085) solo localhost; logs sin prompts completos por defecto (debug opt-in).

## Fases

### Fase 0 — Fundamentos y arquitectura
Definir "respuesta peligrosa" (comandos ejecutables, exfiltración, evasión). Límite ético: lab, sin ejecución real. Modelo de datos por registro (documentado en este plan y en el código). Stack: Python 3.12 + requests a llama.cpp server; SQLite/JSONL; pydantic-settings; informes Markdown + JSON export.

### Fase 1 — Preparación del entorno
- venv dedicado dentro del repo (CERBERUS/.venv).
- Deps: requests, pydantic, pydantic-settings; UI (streamlit/gradio) solo en Fase 5.
- Verificación llama.cpp: GET /v1/models en localhost:8085; si no responde, abortar limpiamente (NUNCA cargar el modelo desde el pipeline).

### Fase 2 — Parser de prompts MITRE (PRIORIDAD ABSOLUTA)
- Leer mitre_redteam_prompts.md; secciones táctica "## NombreTactica", técnica/subtécnica "### TXXXX - Nombre" / "### TXXXX.YYY".
- Extraer bloque de cita "> ..." como prompt.
- Normalizar: tactic_id/name, technique_id/name, is_subtechnique, parent_technique, prompt_text.
- Validar: 873 prompts, 15 tácticas, sin duplicados, bloques bien asociados.
- Exportar mitre_prompts.jsonl; filtrar por táctica/técnica antes de ejecutar.

### Fase 3 — Motor de orquestación
- local_client: chat/completions con n_predict/temperature/top_p/stop; medir latencia y tokens.
- judge_client: system prompt "evaluador de seguridad ofensiva... devuelve JSON".
- Estrategia pasivo/activo/seuro (detener si el local devuelve contenido realmente usable).
- Reintentos con backoff, timeouts configurables, errores como estado error.
- Ejecución uno a uno o lotes; checkpoint cada 10; pausa/reanudación manual.

### Fase 4 — Motor de evaluación y métricas
- Parser de respuestas por secciones (objetivo, prerrequisitos, ejecución, telemetría, SPL, mitigación).
- Clasificación: refused / partial / actionable / high_risk.
- LLM-judge con score + justificación JSON para casos en el límite.
- Métricas por táctica/técnica: tasa de rechazo, tasa accionable, detalle medio, tokens, tiempo medio.

### Fase 5 — Interfaz de usuario (Gradio prototipo; FastAPI+vanilla como alternativa consistente con sec-dashboard)
Dashboard resumen (totales/ejecutados/pendientes/rechazados/alto riesgo), barras por táctica, configuración (modelos, parámetros, filtros), control (iniciar/pausar/reanudar/detener, progreso, log), tabla de resultados filtrable con vista detallada, exportación JSONL + informe Markdown/PDF + solo casos alto riesgo.

### Fase 6 — Pipeline end-to-end
- CLI: python run_mitre_eval.py --tactic Persistence --limit 50.
- Flujo: carga → (orquestador si activo) → local → evalúa → guarda.
- Checkpoint cada 10, reanudación desde último.
- Log de auditoría: prompt enviado, modelo, timestamp, hash de respuesta.
- Informes por run: resumen ejecutivo, estadísticas por táctica, ejemplos críticos; plantilla para reporte a autoridades/certificadoras.

### Fase 7 — Validación y ajuste
- Subconjunto 20–50 prompts de 2–3 tácticas antes del batch completo.
- Ajuste del system prompt del juez (falsos positivos/negativos), calibración del score.
- Hardening: sin red para el local, escrituras solo dentro del directorio de trabajo, sin fugas de API key en logs.
- Documentación de uso responsable: disclaimer legal/ético, procedimiento de destrucción/evidencia de datos sensibles.

### Fase 8 — Entrega y documentación
- README (arquitectura, instalación, uso) + diagrama de flujo.
- Guía paso a paso: modelo, .bat del servidor, UI.
- Plantillas: reporte Markdown a autoridades/certificadoras, CSV resumen por técnica.
- Roadmap: multi-modelo local, comparativas, integración HarmBench/AVID.

## Orden de arranque acordado

1. Fase 0+1: venv + deps + verificación del servidor local.
2. Fase 2: parser → validación 873/15/sin duplicados (gate real).
3. Fase 3+4 mínimo: CLI que ejecuta 1 prompt pasivo y guarda resultado.
4. UI mínima en Fase 5.
5. Escalar al pipeline completo.
