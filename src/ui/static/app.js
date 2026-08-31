// CERBERUS UI — Fase 5a. Vanilla JS, sin dependencias.
// Datos: /api/stats (dashboard) + /api/results (tabla) + /api/results/{i} (detalle).

const PAGE_SIZE = 50;

const state = {
  rows: [], filtered: [], page: 0, detailIdx: null,
  sanitize: true, demo: localStorage.getItem("cerberus-demo") === "1",
  phase: "passive", source: null, // source = run_id que puebla el panel (null = canónico)
};

const $ = (id) => document.getElementById(id);

// ------------------------------------------------- estado visual / toasts --
const STATUS_CLASS = { completed: "b-ok", running: "b-run", pending: "b-run", cancelled: "b-bad", error: "b-bad", aborted: "b-bad" };

function badgeHTML(status) {
  return `<span class="badge ${STATUS_CLASS[status] || ""}">${status}</span>`;
}

function setRunStatus(text, kind) {
  const el = $("run-status");
  if (kind === "muted") { el.className = "muted"; el.textContent = text; return; }
  const cls = kind === "ok" ? "b-ok" : kind === "run" ? "b-run" : "b-bad";
  el.className = "";
  el.innerHTML = `<span class="badge ${cls}">${text}</span>`;
}

function showProgress(done, total) {
  $("run-progress").classList.remove("hidden");
  $("run-progress-bar").style.width = `${total ? Math.round((100 * done) / total) : 0}%`;
}

function hideProgress() { $("run-progress").classList.add("hidden"); }

function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast t-${kind}`;
  el.textContent = msg;
  el.addEventListener("click", () => el.remove());
  $("toasts").append(el);
  setTimeout(() => el.remove(), 8000);
}

// Iconos sol/luna: en oscuro se ve el sol (clic -> claro), en claro la luna (clic -> oscuro).
const THEME_ICONS = {
  dark: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.5l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  light: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
};

function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  $("theme-toggle").innerHTML = THEME_ICONS[t] || THEME_ICONS.dark;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- cards ----
function card(label, value, sub) {
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>` +
    (sub ? `<div class="sub">${sub}</div>` : "");
  return div;
}

// Poblado del dashboard desde un fichero concreto: canónico (runId=null)
// o el results.jsonl de una verificación terminada.
async function loadDashboard(runId) {
  const q = runId ? `?run=${encodeURIComponent(runId)}` : "";
  const [stats, rows] = await Promise.all([fetchJSON(`/api/stats${q}`), fetchJSON(`/api/results${q}`)]);
  if (!runId && stats.status === "no_data") { renderNoData(stats.message); return; }
  state.rows = rows;
  state.page = 0;
  state.source = runId || null;
  renderStats(runId ? { ...stats, source: `${runId} · nueva verificación` } : stats);
  const fe = $("f-estado");
  fe.innerHTML = `<option value="">todos</option>`;
  for (const e of new Set(rows.map((r) => r.estado))) {
    const o = document.createElement("option");
    o.value = e; o.textContent = e;
    fe.append(o);
  }
  renderTable();
}

function renderStats(s) {
  $("src-name").textContent = `(${s.source}, ${s.total} prompts)`;
  if (!s.total) { // run sin registros aún: no pintar con totales a cero
    $("cards").innerHTML = ""; $("tactic-chart").innerHTML = ""; $("detail-dist").innerHTML = "";
    renderTable(); return;
  }
  const c = $("cards");
  c.innerHTML = "";
  c.append(
    card("Prompts", s.total, Object.entries(s.estados).map(([k, v]) => `${v} ${k}`).join(", ")),
    card("Harm media / mediana", `${s.harm.mean} / ${s.harm.median}`, `min ${s.harm.min} · max ${s.harm.max}`),
  );
  for (const [k, v] of Object.entries(s.buckets)) {
    c.append(card(`Bucket ${k}`, v, `${(100 * v / s.total).toFixed(1)}% del total`));
  }
  c.append(
    card("Latencia mediana / p95", `${s.latency_ms.median} / ${s.latency_ms.p95}`, "ms por prompt"),
    card("Tokens generados", s.tokens_out_total.toLocaleString("es"), `media ${Math.round(s.tokens_out_mean).toLocaleString("es")} tok/prompt`),
  );

  // Distribución detail_level (barras HTML, no SVG)
  const dist = $("detail-dist");
  dist.innerHTML = "";
  const maxN = Math.max(...Object.values(s.detail_level));
  for (const [k, v] of Object.entries(s.detail_level)) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<span class="k">detail ${k}</span><span class="bar" style="width:${(100 * v) / maxN}px"></span><span class="n">${v}</span>`;
    dist.append(row);
  }

  // Gráfico de barras por táctica (SVG a mano)
  const wrap = $("tactic-chart");
  const tacs = s.tactics;
  const rowH = 26, labelW = 150, valueW = 190, barMax = 420;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${labelW + barMax + valueW} ${tacs.length * rowH}`);
  tacs.forEach((t, i) => {
    const y = i * rowH;
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", labelW - 8);
    label.setAttribute("y", y + 17);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "bar-label");
    label.textContent = t.tactic;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", labelW);
    rect.setAttribute("y", y + 6);
    rect.setAttribute("width", (t.harm_mean * barMax).toFixed(1));
    rect.setAttribute("height", rowH - 12);
    rect.setAttribute("rx", "3");
    rect.setAttribute("class", "bar-rect");
    const val = document.createElementNS("http://www.w3.org/2000/svg", "text");
    val.setAttribute("x", labelW + t.harm_mean * barMax + 8);
    val.setAttribute("y", y + 17);
    val.setAttribute("class", "bar-value");
    val.textContent = `${t.harm_mean.toFixed(3)} · ${t.pct_ge_0_7}% >= 0.7 · ${t.prompts} prompts`;
    svg.append(label, rect, val);
  });
  wrap.innerHTML = "";
  wrap.append(svg);

  // Rellena selects de filtro (reconstruidos antes: puede repintarse tras vaciar/rellenar)
  const ft = $("f-tactic");
  ft.innerHTML = `<option value="">todas</option>`;
  for (const t of tacs) {
    const o = document.createElement("option");
    o.value = t.tactic;
    o.textContent = t.tactic;
    ft.append(o);
  }
}

// ---------------------------------------------------------------- tabla -----
function harmFilter(v, h) {
  if (!v) return true;
  if (v === "lt03") return h < 0.3;
  if (v === "b0305") return h >= 0.3 && h < 0.5;
  if (v === "b0507") return h >= 0.5 && h < 0.7;
  if (v === "ge07") return h >= 0.7;
  return true;
}

// Estado vacio: no hay results_*.jsonl en data/ (home limpio / clon sin datos).
function renderNoData(msg) {
  state.rows = []; state.filtered = []; state.page = 0;
  state.detailIdx = null; state.source = null;
  $("src-name").textContent = "";
  const c = $("cards");
  c.innerHTML = "";
  c.append(card("Estado", "no_data", msg || ""));
  $("tactic-chart").innerHTML = "";
  $("detail-dist").innerHTML = "";
  const fe = $("f-estado");
  fe.innerHTML = `<option value="">todos</option>`;
  renderTable("No hay resultados disponibles");
  $("detail").classList.add("hidden");
  $("back-top").classList.add("hidden");
}

// Paginacion de 50 en 50: el DOM solo lleva la pagina actual, no las 875.
function renderTable(emptyMsg) {
  const t = $("f-tactic").value, h = $("f-harm").value, e = $("f-estado").value;
  state.filtered = state.rows.filter(
    (r) => (!t || r.tactic === t) && harmFilter(h, r.harm) && (!e || r.estado === e)
  );
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  if (state.page > pages - 1) state.page = 0;
  const start = state.page * PAGE_SIZE;
  const slice = state.filtered.slice(start, start + PAGE_SIZE);
  const body = $("results-body");
  body.innerHTML = "";
  for (const r of slice) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.i}</td><td>${r.tactic}</td><td>${r.technique}</td>` +
      `<td>${r.subtechnique ?? "—"}</td>` +
      `<td class="${r.estado === "success" ? "ok" : ""}">${r.estado}</td>` +
      `<td class="${r.harm >= 0.7 ? "harm-hi" : ""}">${r.harm.toFixed(3)}</td>` +
      `<td>${r.detail}</td><td>${r.tokens_out.toLocaleString("es")}</td><td>${r.latency_ms.toLocaleString("es")}</td>`;
    tr.addEventListener("click", () => showDetail(r.i));
    body.append(tr);
  }
  if (!state.rows.length) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="9">${emptyMsg || "Sin verificación en curso — el panel se poblará al terminar un run"}</td>`;
    body.append(tr);
  }
  $("table-count").textContent = `${state.filtered.length} de ${state.rows.length} filas`;
  $("page-info").textContent = slice.length
    ? `pagina ${state.page + 1}/${pages} (${start + 1}-${start + slice.length})`
    : "sin resultados";
  $("pg-prev").disabled = state.page === 0;
  $("pg-next").disabled = state.page >= pages - 1 || !slice.length;
}

// Vaciar el panel hasta que termine una nueva verificación (no toca el disco).
function wipePanel() {
  state.rows = []; state.filtered = []; state.page = 0;
  state.detailIdx = null; state.source = null;
  $("cards").innerHTML = "";
  $("tactic-chart").innerHTML = "";
  $("detail-dist").innerHTML = "";
  $("src-name").textContent = "(panel vacío — se poblará al terminar una nueva verificación)";
  const fe = $("f-estado");
  fe.innerHTML = `<option value="">todos</option>`;
  renderTable();
  $("detail").classList.add("hidden");
  $("back-top").classList.add("hidden");
  toast("Panel vaciado: quedará así hasta que termine una verificación (run).", "warn");
}

// ---------------------------------------------------------------- detalle ---
async function showDetail(i) {
  state.detailIdx = i;
  const qs = new URLSearchParams({ sanitize: state.sanitize ? "1" : "0" });
  if (state.source) qs.set("run", state.source);
  const d = await fetchJSON(`/api/results/${i}?${qs}`);
  $("d-technique").textContent = `— ${d.technique}${d.subtechnique ? "." + d.subtechnique : ""} (${d.tactic})`;
  $("d-meta").textContent =
    `estado: ${d.estado} · run_id: ${d.run_id ?? "—"} · modelo local: ${d.modelo_local ?? "—"}` +
    (d.sanitized ? " · respuestas sanitizadas" : " · RESPUESTAS REALES");
  const demoNote = "(oculto en modo demo: solo metricas; desmarca la casilla de modo demo para verlo)";
  $("d-prompt").textContent = state.demo ? demoNote : d.prompt_original;
  const enviadoDiff = d.prompt_enviado && d.prompt_enviado !== d.prompt_original;
  $("d-enviado-wrap").classList.toggle("hidden", !enviadoDiff || state.demo);
  if (enviadoDiff && !state.demo) $("d-enviado").textContent = d.prompt_enviado;
  $("d-respuesta").textContent = state.demo ? demoNote : d.respuesta_cruda;

  const m = $("d-metrics");
  m.innerHTML = "";
  for (const [k, v] of Object.entries(d.metricas)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th>${k}</th><td>${typeof v === "number" ? v.toLocaleString("es") : v}</td>`;
    m.append(tr);
  }
  const htr = document.createElement("tr");
  htr.innerHTML = `<th>hash_respuesta</th><td>${d.hash_respuesta ?? "—"}</td>`;
  m.append(htr);

  $("detail").classList.remove("hidden");
  $("back-top").classList.remove("hidden");
  $("detail").scrollIntoView({ behavior: "smooth" });
}

// ------------------------------------------------------------- reportes ----
async function loadReports() {
  const reports = await fetchJSON("/api/reports");
  const ul = $("report-list");
  for (const [key, filename] of Object.entries(reports)) {
    const li = document.createElement("li");
    li.innerHTML = `<a href="/api/reports/${key}" download>${filename}</a>`;
    ul.append(li);
  }
}

// ---------------------------------------------------------------- runner ---
const runState = { id: null, es: null };

async function loadJudgeConfig() {
  const cfg = await fetchJSON("/api/config/judge");
  $("j-base-url").placeholder = cfg.base_url_default || "https://openrouter.ai/api/v1";
  if (cfg.model_default) $("j-model").placeholder = cfg.model_default;
  if (!cfg.configured) {
    $("use-judge").disabled = true;
    $("judge-status").textContent =
      "falta JUDGE_API_KEY en el entorno de la UI: el juez no se puede usar (la key nunca viaja por la UI).";
  } else {
    $("judge-status").textContent = "juez disponible (key en env); se dispara al terminar el run si marcas la casilla.";
  }
}

function consoleLine(msg) {
  const el = $("console");
  const t = new Date().toLocaleTimeString("es");
  el.textContent += `[${t}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}

function fmtEvent(ev) {
  if (ev.type === "start") return `INICIO run ${ev.run_id}: ${ev.total} prompts (${ev.resumed} reanudados)`;
  if (ev.type === "record")
    return `${ev.done}/${ev.total} ${ev.technique} ${ev.estado} harm=${ev.harm} tok_out=${ev.tokens_out} lat=${ev.latency_ms}ms ETA ${ev.eta_h}h`;
  if (ev.type === "done") return `FIN run: harm_medio=${ev.summary.harm_medio} duracion=${ev.summary.duracion_h}h`;
  if (ev.type === "abort") return `ABORT: ${ev.reason}`;
  if (ev.type === "cancelled") return `CANCELADO entre prompts (checkpoint ${ev.done})`;
  if (ev.type === "error") return `ERROR: ${ev.reason || JSON.stringify(ev)}`;
  if (ev.type === "state") return `estado guardado: ${ev.run.status} checkpoint=${ev.run.checkpoint_idx}`;
  return JSON.stringify(ev);
}

function setRunButtons(active, resumable) {
  $("btn-start").disabled = active;
  $("btn-cancel").disabled = !active;
  $("btn-resume").disabled = !resumable;
}

function openSSE(runId) {
  if (runState.es) runState.es.close();
  const es = new EventSource(`/events/run/${runId}`);
  runState.es = es;
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    consoleLine(fmtEvent(ev));
    if (ev.type === "start") showProgress(0, ev.total);
    if (ev.type === "record") showProgress(ev.done, ev.total);
    if (["done", "abort", "cancelled", "error"].includes(ev.type)) {
      es.close();
      hideProgress();
      const what = state.phase === "judge" ? "juez" : "run";
      const kind = ev.type === "done" ? "ok" : "bad";
      setRunStatus(`${what} ${ev.type}`, kind);
      toast(
        ev.type === "done"
          ? `${what} ${runId} terminado`
          : ev.type === "cancelled"
            ? `run ${runId} cancelado (checkpoint ${ev.done ?? "?"})`
            : `${what} ${runId}: ${ev.type} — ${ev.reason || ""}`,
        kind
      );
      if (state.phase === "passive") {
        setRunButtons(false, ev.type !== "done");
        maybeJudge(runId);
        if (ev.type === "done")
          loadDashboard(runId).catch((e) => toast(`no se pudo poblar el panel con ${runId}: ${e.message}`, "bad"));
      } else {
        state.phase = "passive";
        setRunButtons(false, false);
      }
    }
  };
  es.onerror = () => {
    // EventSource reintenta solo; si el run ya no existe, cerramos.
    fetch(`/api/runs`).then((r) => r.json()).then((rows) => {
      const live = rows.find((x) => x.run_id === runId && x.live);
      if (!live) { es.close(); setRunButtons(false, false); }
    }).catch(() => {});
  };
}

// Si el usuario marco la casilla del juez, se dispara tras el run pasivo.
async function maybeJudge(runId) {
  const box = $("use-judge");
  if (!box.checked || box.disabled) return;
  state.phase = "judge";
  setRunButtons(true, false);
  setRunStatus(`juez en curso (${runId})`, "run");
  const body = {
    base_url: $("j-base-url").value.trim() || null,
    model: $("j-model").value.trim() || null,
  };
  consoleLine(`POST /api/run/${runId}/judge ${JSON.stringify(body)}`);
  const r = await fetch(`/api/run/${runId}/judge`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) {
    consoleLine(`juez ERROR ${r.status}: ${d.detail}`);
    state.phase = "passive";
    setRunButtons(false, false);
    setRunStatus(`juez no lanzado (${r.status})`, "bad");
    toast(`juez no lanzado: ${d.detail}`, "bad");
    return;
  }
  openSSE(runId); // la cola del job de juez publica en el mismo /events/run/<id>
}

async function startRun() {
  const body = {
    tactic: $("p-tactic").value || null,
    technique: $("p-technique").value.trim() || null,
    limit: parseInt($("p-limit").value, 10) || 0,
    max_tokens: parseInt($("p-max-tokens").value, 10),
    repeat_penalty: parseFloat($("p-repeat-penalty").value),
    temperature: parseFloat($("p-temperature").value),
    local_base_url: $("p-local-url").value.trim() || null,
  };
  state.phase = "passive";
  $("console").textContent = "";
  consoleLine(`POST /api/run ${JSON.stringify(body)}`);
  const r = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) {
    consoleLine(`ERROR ${r.status}: ${d.detail}`);
    toast(`run no lanzado (${r.status}): ${d.detail}`, "bad");
    return;
  }
  runState.id = d.run_id;
  setRunStatus(`run en curso (${d.run_id})`, "run");
  setRunButtons(true, false);
  openSSE(d.run_id);
}

async function cancelRun() {
  if (!runState.id) return;
  const r = await fetch(`/api/run/${runState.id}/cancel`, { method: "POST" });
  consoleLine(`cancel -> ${r.status}`);
}

async function resumeRun() {
  if (!runState.id) return;
  $("console").textContent = "";
  const r = await fetch(`/api/run/${runState.id}/resume`, { method: "POST" });
  const d = await r.json();
  if (!r.ok) {
    consoleLine(`ERROR ${r.status}: ${d.detail}`);
    toast(`reanudar falló (${r.status}): ${d.detail}`, "bad");
    return;
  }
  setRunStatus(`reanudando (${runState.id})`, "run");
  setRunButtons(true, false);
  openSSE(runState.id);
}

async function refreshRuns() {
  const rows = await fetchJSON("/api/runs");
  const live = rows.find((x) => x.live);
  if (live) {
    runState.id = live.run_id;
    setRunStatus(`en curso (${live.run_id})`, "run");
    setRunButtons(true, false);
    openSSE(live.run_id);
  } else {
    const last = rows[0];
    if (last) runState.id = last.run_id; // habilita Reanudar si aplica
    setRunStatus("sin run activo", "muted");
    hideProgress();
    setRunButtons(false, !!last && ["cancelled", "aborted", "error"].includes(last.status));
  }
}

// ---------------------------------------------------------- comparar runs --
// Mezcla la BD de la UI y el escaneo de disco (los runs hechos por CLI no estan en la BD).
function mergeRunLists(dbRows, diskRows) {
  const map = new Map();
  for (const r of diskRows) map.set(r.run_id, { run_id: r.run_id, status: "(fuera de la UI)", has_merged: r.has_merged });
  for (const r of dbRows) map.set(r.run_id, { ...map.get(r.run_id), ...r, has_merged: map.get(r.run_id)?.has_merged ?? false });
  return [...map.values()].sort((x, y) => (y.run_id > x.run_id ? 1 : -1));
}

function fillCompareSelects(rows) {
  for (const id of ["cmp-a", "cmp-b"]) {
    const sel = $(id);
    sel.innerHTML = "";
    for (const r of rows) {
      const o = document.createElement("option");
      o.value = r.run_id;
      o.dataset.status = r.status;
      o.textContent = `${r.run_id} (${r.status})${r.has_merged ? " [juez]" : ""}`;
      sel.append(o);
    }
  }
  updateCmpBadges();
}

function updateCmpBadges() {
  for (const [selId, badgeId] of [["cmp-a", "cmp-a-badge"], ["cmp-b", "cmp-b-badge"]]) {
    const o = $(selId).selectedOptions[0];
    const b = $(badgeId);
    if (!o) { b.classList.add("hidden"); continue; }
    b.innerHTML = badgeHTML(o.dataset.status || "(fuera de la UI)");
    b.classList.remove("hidden");
  }
}

async function compareRuns() {
  const a = $("cmp-a").value, b = $("cmp-b").value;
  if (!a || !b) return;
  let d;
  try {
    const r = await fetch(`/api/runs/${a}/compare/${b}`);
    d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
  } catch (err) {
    $("cmp-summary").innerHTML = `<tr><th>Error</th><td>${err.message}</td></tr>`;
    $("comparison").classList.remove("hidden");
    return;
  }
  const sum = $("cmp-summary");
  sum.innerHTML = "";
  const htr = document.createElement("tr");
  htr.innerHTML = `<th></th><th>A: ${d.a.run_id}</th><th>B: ${d.b.run_id}</th>`;
  sum.append(htr);
  const row2 = (k, va, vb) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th>${k}</th><td>${va ?? "—"}</td><td>${vb ?? "—"}</td>`;
    sum.append(tr);
  };
  row2("total", d.a.total, d.b.total);
  row2("harm heur. media / mediana",
       `${d.a.harm_heuristic.mean} / ${d.a.harm_heuristic.median}`,
       `${d.b.harm_heuristic.mean} / ${d.b.harm_heuristic.median}`);
  row2("harm final (con juez)",
       d.a.has_judge ? `${d.a.harm_final.mean} / ${d.a.harm_final.median}` : "sin juez",
       d.b.has_judge ? `${d.b.harm_final.mean} / ${d.b.harm_final.median}` : "sin juez");
  row2("juez: puntuados / subidos",
       d.a.has_judge ? `${d.a.judged} / ${d.a.upgraded_by_judge}` : "—",
       d.b.has_judge ? `${d.b.judged} / ${d.b.upgraded_by_judge}` : "—");
  const clsOf = (v) => (v !== null && v > 0 ? "harm-hi" : v !== null && v < 0 ? "ok" : "");
  const tb = $("cmp-tactics-body");
  tb.innerHTML = "";
  for (const t of d.per_tactic) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${t.tactic}</td><td>${t.a_n}</td><td>${t.a_mean ?? "—"}</td>` +
      `<td>${t.b_n}</td><td>${t.b_mean ?? "—"}</td><td class="${clsOf(t.diff)}">${t.diff ?? "—"}</td>`;
    tb.append(tr);
  }
  const ttb = $("cmp-techs-body");
  ttb.innerHTML = "";
  for (const t of d.per_technique) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${t.tactic}</td><td>${t.technique}</td>` +
      `<td>${t.a_harm ?? "—"}</td><td>${t.b_harm ?? "—"}</td><td class="${clsOf(t.diff)}">${t.diff ?? "—"}</td>`;
    ttb.append(tr);
  }
  $("comparison").classList.remove("hidden");
}

// ------------------------------------------------------------------ init ----
document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadDashboard(null);

    // Filtros: al cambiar, volver a la pagina 1
    const onFilter = () => { state.page = 0; renderTable(); };
    $("f-tactic").addEventListener("change", onFilter);
    $("f-harm").addEventListener("change", onFilter);
    $("f-estado").addEventListener("change", onFilter);
    $("pg-prev").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); renderTable(); });
    $("pg-next").addEventListener("click", () => {
      const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
      if (state.page < pages - 1) { state.page++; renderTable(); }
    });

    // Tema claro/oscuro (persistente)
    applyTheme(document.documentElement.dataset.theme || "dark");
    $("theme-toggle").addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      localStorage.setItem("cerberus-theme", next);
      applyTheme(next);
    });

    // Modo demo (persistente)
    $("demo-toggle").checked = state.demo;
    $("demo-toggle").addEventListener("change", (ev) => {
      state.demo = ev.target.checked;
      localStorage.setItem("cerberus-demo", state.demo ? "1" : "0");
      if (state.detailIdx !== null) showDetail(state.detailIdx);
    });

    $("sanitize-toggle").checked = state.sanitize;
    $("sanitize-toggle").addEventListener("change", (ev) => {
      state.sanitize = ev.target.checked;
      if (state.detailIdx !== null) showDetail(state.detailIdx);
    });

    // Runner: mismo desplegable de tácticas que el filtro de tabla.
    for (const o of [...$("f-tactic").options]) {
      const no = document.createElement("option");
      no.value = o.value; no.textContent = o.textContent;
      $("p-tactic").append(no);
    }
    await loadReports();
    await loadJudgeConfig();

    const [dbRows, diskRows] = await Promise.all([fetchJSON("/api/runs"), fetchJSON("/api/runs/scan")]);
    fillCompareSelects(mergeRunLists(dbRows, diskRows));
    $("cmp-a").addEventListener("change", updateCmpBadges);
    $("cmp-b").addEventListener("change", updateCmpBadges);
    $("btn-compare").addEventListener("click", compareRuns);

    $("btn-wipe").addEventListener("click", wipePanel);
    $("btn-start").addEventListener("click", startRun);
    $("btn-cancel").addEventListener("click", cancelRun);
    $("btn-resume").addEventListener("click", resumeRun);
    await refreshRuns();
  } catch (err) {
    document.body.innerHTML = `<p class="notice">Error cargando datos: ${err.message}</p>`;
  }
});
