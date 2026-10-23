/* CERBERUS UI — frontend sin dependencias.
   Todo el texto de datos se pinta con textContent: nada de innerHTML con datos. */

"use strict";

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";

const PAGE_SIZE = 50;
const MAX_CONSOLE_LINES = 400;
const UI_VERSION = "3";

const state = {
  rows: [],
  filtered: [],
  page: 0,
  sort: { key: "i", dir: 1 },
  filters: { run: "", tactic: "", harm: "", estado: "", q: "" },
  source: null,
  detailIdx: null,
  demo: localStorage.getItem("cerberus-demo") === "1",
  sanitize: true,
  run: { id: null, active: false, total: 0 },
  judge: { configured: false, defaultBase: "", defaultModel: "" },
  local: { ok: false, base: "", models: [], error: "" },
  comparison: null,
  reports: [],
  serverTimer: null,
  es: null,
};

/* ------------------------------------------------------------- utilidades */

const fmtInt = (n) => Number(n ?? 0).toLocaleString("es-ES");
const fmtNum = (n, d = 3) => (typeof n === "number" ? n.toFixed(d) : "—");

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = String(text);
  if (cls) n.className = cls;
  return n;
}

function svg(tag, attrs) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
  return n;
}

function showBanner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.remove("hidden");
}

function hideBanner() {
  $("banner").classList.add("hidden");
}

function toast(msg, kind = "info", ms = 4200) {
  const t = el("div", msg, "toast " + kind);
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    showBanner("No se pudo conectar con la UI: " + e.message);
    throw e;
  }
  if (r.status === 401) {
    // Carrera al primer arranque: la cookie se fija en la respuesta de /. Reintento.
    await new Promise((ok) => setTimeout(ok, 250));
    r = await fetch(path, opts);
  }
  if (r.status === 401) {
    showBanner("Sesion no valida. Recarga la pagina (Ctrl+R) para recibir el token local.");
    throw new Error("401 sin token de sesion");
  }
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const body = await r.json();
      detail = body.detail || detail;
    } catch (e) { /* respuesta sin JSON */ }
    throw new Error(detail);
  }
  hideBanner();
  return r.json();
}

function confirmAction(title, text) {
  return new Promise((resolve) => {
    const dlg = $("confirm");
    $("confirm-title").textContent = title;
    $("confirm-text").textContent = text;
    dlg.returnValue = "";
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.showModal();
  });
}

/* ------------------------------------------------------------------ tema */

const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg>';
const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z"/></svg>';

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $("theme-toggle");
  btn.innerHTML = theme === "light" ? ICON_MOON : ICON_SUN;
  btn.title = theme === "light" ? "Cambiar a oscuro" : "Cambiar a claro";
}

function initTheme() {
  applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  $("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    localStorage.setItem("cerberus-theme", next);
    applyTheme(next);
  });
}

/* -------------------------------------------------------------- navegacion */

function initNav() {
  const links = [...document.querySelectorAll(".side a")];
  const sections = links
    .map((a) => document.querySelector(a.getAttribute("href")))
    .filter(Boolean);
  const setActive = (id) => links.forEach((l) => l.classList.toggle("active", l.getAttribute("href") === "#" + id));
  if ("IntersectionObserver" in window) {
    const spy = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
    }, { rootMargin: "-15% 0px -65% 0px", threshold: 0 });
    sections.forEach((s) => spy.observe(s));
  }
}

/* --------------------------------------------------------------- dashboard */

function renderCards(stats) {
  const host = $("cards");
  host.textContent = "";
  const ge7 = stats.buckets?.[">=0.7"] ?? 0;
  const pct = stats.total ? (100 * ge7) / stats.total : 0;
  const cards = [
    ["Prompts evaluados", fmtInt(stats.total), stats.source || ""],
    ["Harm medio", fmtNum(stats.harm?.mean), "0 – 1"],
    ["Harm mediana", fmtNum(stats.harm?.median), "p50"],
    ["Harm ≥ 0.7", fmtInt(ge7), pct.toFixed(1) + "% del total"],
    ["Latencia mediana", fmtInt(stats.latency_ms?.median) + " ms", "p95 " + fmtInt(stats.latency_ms?.p95) + " ms"],
    ["Tokens de salida", fmtInt(stats.tokens_out_mean), "total " + fmtInt(stats.tokens_out_total)],
  ];
  for (const [label, value, sub] of cards) {
    const c = el("div", undefined, "card");
    c.appendChild(el("div", label, "label"));
    c.appendChild(el("div", value, "value"));
    if (sub) c.appendChild(el("div", sub, "sub"));
    host.appendChild(c);
  }
}

function renderChart(tactics) {
  const host = $("tactic-chart");
  host.textContent = "";
  if (!tactics || !tactics.length) {
    host.appendChild(el("p", "Sin datos para este run.", "muted"));
    return;
  }
  const W = 380, rowH = 26, padL = 128, padR = 44, barMax = W - padL - padR;
  const H = tactics.length * rowH + 4;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  root.appendChild(svg("title", {})).textContent = "Harm medio por tactica";

  tactics.forEach((t, idx) => {
    const y = idx * rowH + rowH / 2;
    const label = svg("text", { x: 0, y: y + 4, class: "bar-label" });
    label.textContent = t.tactic.length > 18 ? t.tactic.slice(0, 17) : t.tactic;
    const ttl = svg("title", {});
    ttl.textContent = `${t.tactic}: ${fmtNum(t.harm_mean)} (${t.prompts} prompts)`;
    label.appendChild(ttl);
    root.appendChild(label);

    const track = svg("rect", {
      x: padL, y: y - 5, width: barMax, height: 10, rx: 5,
      fill: "var(--surface-3)",
    });
    root.appendChild(track);

    const w = Math.max(2, Math.min(1, t.harm_mean) * barMax);
    root.appendChild(svg("rect", {
      x: padL, y: y - 5, width: w, height: 10, rx: 5, class: "bar-rect",
    }));

    const value = svg("text", { x: W - 2, y: y + 4, class: "bar-value", "text-anchor": "end" });
    value.textContent = fmtNum(t.harm_mean);
    root.appendChild(value);
  });
  host.appendChild(root);
}

function renderDist(dist) {
  const host = $("detail-dist");
  host.textContent = "";
  const entries = Object.entries(dist || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  for (const [k, v] of entries) {
    const row = el("div", undefined, "row");
    row.appendChild(el("span", "detail " + k, "k"));
    const track = el("div", undefined, "bar-track");
    const bar = el("div", undefined, "bar");
    bar.style.width = (100 * v) / max + "%";
    track.appendChild(bar);
    row.appendChild(track);
    row.appendChild(el("span", fmtInt(v), "n"));
    host.appendChild(row);
  }
}

async function loadDashboard(runId) {
  const q = runId ? `?run=${encodeURIComponent(runId)}` : "";
  try {
    const [stats, rows] = await Promise.all([api("/api/stats" + q), api("/api/results" + q)]);
    state.source = runId || null;
    state.rows = rows;
    state.page = 0;
    if (stats.status === "no_data") {
      $("src-name").textContent = "sin datos";
      $("cards").textContent = "";
      $("tactic-chart").textContent = "";
      $("detail-dist").textContent = "";
      $("cards").appendChild(el("p", stats.message || "No hay datos.", "muted"));
      state.filtered = [];
      renderTable();
      return;
    }
    $("src-name").textContent = `${stats.source || "canonico"} · ${fmtInt(stats.total)} prompts`;
    renderCards(stats);
    renderChart(stats.tactics);
    renderDist(stats.detail_level);
    fillTacticOptions(stats.tactics || []);
    fillEstadoOptions(rows);
    renderTable();
  } catch (e) {
    toast("No se pudo cargar el dashboard: " + e.message, "bad");
  }
}

function fillEstadoOptions(rows) {
  const sel = $("f-estado");
  const current = sel.value;
  sel.textContent = "";
  sel.appendChild(new Option("todos", ""));
  for (const e of new Set(rows.map((r) => r.estado))) sel.appendChild(new Option(e, e));
  sel.value = current;
}

/* ------------------------------------------------------------------ tabla */

function harmBucket(h) {
  if (h < 0.3) return "lt03";
  if (h < 0.5) return "b0305";
  if (h < 0.7) return "b0507";
  return "ge07";
}

function applyFilters() {
  const f = state.filters;
  const q = f.q.toLowerCase();
  state.filtered = state.rows.filter((r) => {
    if (f.tactic && r.tactic !== f.tactic) return false;
    if (f.harm && harmBucket(r.harm) !== f.harm) return false;
    if (f.estado && r.estado !== f.estado) return false;
    if (q) {
      const hay = `${r.technique} ${r.subtechnique || ""} ${r.tactic}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const { key, dir } = state.sort;
  state.filtered.sort((a, b) => {
    const va = a[key], vb = b[key];
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va ?? "").localeCompare(String(vb ?? ""), "es") * dir;
  });
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  if (state.page > pages - 1) state.page = pages - 1;
}

function renderTable() {
  applyFilters();
  const body = $("results-body");
  body.textContent = "";
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  const start = state.page * PAGE_SIZE;
  const slice = state.filtered.slice(start, start + PAGE_SIZE);

  for (const r of slice) {
    const tr = document.createElement("tr");
    tr.dataset.i = r.i;
    tr.tabIndex = 0;
    tr.setAttribute("aria-label", `Tecnica ${r.technique}, harm ${fmtNum(r.harm)}`);
    if (state.detailIdx === r.i) tr.classList.add("selected");

    tr.appendChild(el("td", r.i, "num"));
    tr.appendChild(el("td", r.tactic));
    tr.appendChild(el("td", r.technique));
    tr.appendChild(el("td", r.subtechnique || "—"));
    tr.appendChild(el("td", r.estado, r.estado === "success" ? "ok" : "bad"));
    const th = el("td", fmtNum(r.harm), "num" + (r.harm >= 0.7 ? " harm-hi" : ""));
    tr.appendChild(th);
    tr.appendChild(el("td", r.detail, "num"));
    tr.appendChild(el("td", fmtInt(r.tokens_out), "num"));
    tr.appendChild(el("td", fmtInt(r.latency_ms), "num"));

    tr.addEventListener("click", () => openDrawer(r.i));
    tr.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        openDrawer(r.i);
      }
    });
    body.appendChild(tr);
  }

  if (!slice.length) {
    const tr = el("tr", undefined, "empty-row");
    const td = el("td", state.rows.length
      ? "Ningun resultado con estos filtros."
      : "Sin verificacion en curso: el panel se poblara al terminar un run.", undefined);
    td.colSpan = 9;
    tr.appendChild(td);
    body.appendChild(tr);
  }

  $("table-count").textContent = `${fmtInt(state.filtered.length)} de ${fmtInt(state.rows.length)} filas`;
  $("page-info").textContent = slice.length
    ? `pagina ${state.page + 1}/${pages} · ${start + 1}–${start + slice.length}`
    : "sin resultados";
  $("pg-prev").disabled = state.page === 0;
  $("pg-next").disabled = state.page >= pages - 1 || !slice.length;

  for (const th of document.querySelectorAll("th[data-sort]")) {
    const on = th.dataset.sort === state.sort.key;
    th.setAttribute("aria-sort", on ? (state.sort.dir === 1 ? "ascending" : "descending") : "none");
  }
}

function initTable() {
  $("f-tactic").addEventListener("change", (ev) => { state.filters.tactic = ev.target.value; state.page = 0; renderTable(); });
  $("f-harm").addEventListener("change", (ev) => { state.filters.harm = ev.target.value; state.page = 0; renderTable(); });
  $("f-estado").addEventListener("change", (ev) => { state.filters.estado = ev.target.value; state.page = 0; renderTable(); });
  $("f-search").addEventListener("input", (ev) => { state.filters.q = ev.target.value.trim(); state.page = 0; renderTable(); });
  $("f-run").addEventListener("change", (ev) => loadDashboard(ev.target.value || null));

  $("pg-prev").addEventListener("click", () => { if (state.page > 0) { state.page--; renderTable(); } });
  $("pg-next").addEventListener("click", () => { state.page++; renderTable(); });

  for (const th of document.querySelectorAll("th[data-sort]")) {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : 1 };
      renderTable();
    });
  }

  $("btn-wipe").addEventListener("click", async () => {
    const ok = await confirmAction("Vaciar panel", "Se ocultaran la tabla, el detalle y las tarjetas. No se borra nada en disco; se repuebla al terminar un run.");
    if (!ok) return;
    state.rows = [];
    state.filtered = [];
    state.page = 0;
    state.detailIdx = null;
    $("cards").textContent = "";
    $("tactic-chart").textContent = "";
    $("detail-dist").textContent = "";
    $("src-name").textContent = "panel vacio";
    renderTable();
    closeDrawer();
    toast("Panel vaciado. Se repoblara al terminar una verificacion.", "warn");
  });
}

/* ----------------------------------------------------------------- detalle */

async function openDrawer(i) {
  state.detailIdx = i;
  const drawer = $("drawer");
  drawer.hidden = false;
  document.body.classList.add("drawer-open");
  $("drawer-title").textContent = "Cargando…";
  $("drawer-close").focus();
  try {
    const qs = new URLSearchParams({ sanitize: state.sanitize ? "1" : "0" });
    if (state.source) qs.set("run", state.source);
    const d = await api(`/api/results/${i}?${qs}`);
    $("drawer-title").textContent = `${d.technique}${d.subtechnique ? "." + d.subtechnique : ""}`;
    $("d-meta").textContent =
      `${d.tactic} · estado ${d.estado} · run ${d.run_id || "—"} · modelo ${d.modelo_local || "—"}` +
      (d.sanitized ? " · bloques de codigo ocultos" : " · respuestas reales");

    const demoNote = "Contenido oculto en modo demo: solo metricas.";
    $("d-prompt").textContent = state.demo ? demoNote : d.prompt_original;
    const diff = d.prompt_enviado && d.prompt_enviado !== d.prompt_original;
    $("d-enviado-wrap").hidden = !diff || state.demo;
    if (diff && !state.demo) $("d-enviado").textContent = d.prompt_enviado;
    $("d-respuesta").textContent = state.demo ? demoNote : d.respuesta_cruda;

    const m = $("d-metrics");
    m.textContent = "";
    for (const [k, v] of Object.entries(d.metricas || {})) {
      const tr = document.createElement("tr");
      const th = el("th", k);
      th.scope = "row";
      tr.appendChild(th);
      tr.appendChild(el("td", typeof v === "number" ? v.toLocaleString("es-ES") : v));
      m.appendChild(tr);
    }
    const tr = document.createElement("tr");
    tr.appendChild(el("th", "hash_respuesta"));
    tr.appendChild(el("td", d.hash_respuesta || "—"));
    m.appendChild(tr);

    renderTable();
  } catch (e) {
    toast("No se pudo abrir el detalle: " + e.message, "bad");
    closeDrawer();
  }
}

function closeDrawer() {
  const idx = state.detailIdx;
  const drawer = $("drawer");
  drawer.hidden = true;
  document.body.classList.remove("drawer-open");
  state.detailIdx = null;
  const row = idx === null ? null : document.querySelector(`tr[data-i="${idx}"]`);
  if (row) row.focus();
  renderTable();
}

function trapTab(ev) {
  if (ev.key !== "Tab") return;
  const nodes = $("drawer").querySelectorAll(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
  );
  const list = [...nodes].filter((e) => e.offsetParent !== null);
  if (!list.length) return;
  const first = list[0];
  const last = list[list.length - 1];
  if (ev.shiftKey && document.activeElement === first) {
    ev.preventDefault();
    last.focus();
  } else if (!ev.shiftKey && document.activeElement === last) {
    ev.preventDefault();
    first.focus();
  }
}

function initDrawer() {
  $("drawer-close").addEventListener("click", closeDrawer);
  $("drawer").addEventListener("keydown", trapTab);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("drawer").hidden) closeDrawer();
  });

  const tabs = [
    ["tab-prompt", "panel-prompt"],
    ["tab-response", "panel-response"],
    ["tab-metrics", "panel-metrics"],
  ];
  for (const [tabId, panelId] of tabs) {
    $(tabId).addEventListener("click", () => {
      for (const [t, p] of tabs) {
        const active = t === tabId;
        $(t).classList.toggle("active", active);
        $(t).setAttribute("aria-selected", active ? "true" : "false");
        $(p).hidden = !active;
      }
    });
  }

  const refresh = () => { if (state.detailIdx !== null) openDrawer(state.detailIdx); };
  $("demo-toggle").checked = state.demo;
  $("demo-toggle").addEventListener("change", (ev) => {
    state.demo = ev.target.checked;
    localStorage.setItem("cerberus-demo", state.demo ? "1" : "0");
    refresh();
  });
  $("sanitize-toggle").checked = state.sanitize;
  $("sanitize-toggle").addEventListener("change", (ev) => {
    state.sanitize = ev.target.checked;
    refresh();
  });
}

/* ------------------------------------------------------------------ runner */

function consoleLine(text) {
  const pre = $("console");
  const lines = pre.textContent.split("\n");
  lines.push(text);
  if (lines.length > MAX_CONSOLE_LINES) lines.splice(0, lines.length - MAX_CONSOLE_LINES);
  pre.textContent = lines.join("\n");
  pre.scrollTop = pre.scrollHeight;
}

function setRunButtons(active) {
  state.run.active = active;
  $("btn-start").disabled = active || !state.local.ok;
  $("btn-cancel").disabled = !active;
  $("btn-resume").disabled = active;
}

let statusSeq = 0;

async function refreshLocalStatus(quiet) {
  const seq = ++statusSeq;
  $("st-local").querySelector("span").textContent = "Comprobando…";
  try {
    const typed = $("p-local-url").value.trim();
    const q = typed ? "?base_url=" + encodeURIComponent(typed) : "";
    const s = await api("/api/local/status" + q);
    if (seq !== statusSeq) return;  // respuesta vieja: hay otra comprobacion en curso
    state.local = { ok: s.ok, base: s.base_url, models: s.models || [], error: s.error || "" };
    const pill = $("st-local");
    pill.classList.toggle("ok", s.ok);
    pill.classList.toggle("bad", !s.ok);
    pill.querySelector("span").textContent = s.ok ? "Servidor local" : "Servidor local (sin respuesta)";

    const el2 = $("run-server");
    el2.textContent = s.ok
      ? `Conectado a ${s.base_url} · modelos: ${s.models.join(", ") || "sin id"}`
      : `Sin respuesta en ${s.base_url}. Arranca llama.cpp con su .bat. ${s.error || ""}`;

    if (!state.run.active) $("btn-start").disabled = !s.ok;
    if (!quiet && s.ok) toast("Servidor local disponible.", "ok", 2500);
  } catch (e) {
    if (seq !== statusSeq) return;
    $("st-local").querySelector("span").textContent = "Servidor local";
    if (!quiet) toast("No se pudo comprobar el servidor local: " + e.message, "bad");
  }
  clearTimeout(state.serverTimer);
  state.serverTimer = setTimeout(() => refreshLocalStatus(true), 15000);
}

function runPayload() {
  return {
    tactic: $("p-tactic").value || null,
    technique: $("p-technique").value.trim() || null,
    limit: Number($("p-limit").value || 0),
    max_tokens: Number($("p-max-tokens").value || 4096),
    repeat_penalty: Number($("p-repeat-penalty").value || 1.15),
    temperature: Number($("p-temperature").value || 0.2),
    local_base_url: $("p-local-url").value.trim() || null,
  };
}

function attachStream(runId) {
  if (state.es) state.es.close();
  const es = new EventSource(`/events/run/${runId}`);
  state.es = es;
  state.run.id = runId;
  $("run-status").textContent = `run ${runId}`;
  $("run-progress").hidden = false;
  $("run-progress-bar").style.width = "0%";

  es.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch (e) { return; }
    switch (ev.type) {
      case "state":
        if (ev.run) {
          state.run.total = ev.run.checkpoint_idx || 0;
        }
        break;
      case "start":
        state.run.total = ev.total || 0;
        consoleLine(`[start] ${ev.total} prompts${ev.resumed ? ` (${ev.resumed} ya hechos)` : ""}`);
        break;
      case "record": {
        const pct = ev.total ? Math.round((100 * ev.done) / ev.total) : 0;
        $("run-progress-bar").style.width = pct + "%";
        const eta = typeof ev.eta_h === "number" ? ` · ETA ${ev.eta_h} h` : "";
        consoleLine(`[${ev.done}/${ev.total}] ${ev.technique} · ${ev.estado} · harm ${fmtNum(ev.harm)}${eta}`);
        $("run-status").textContent = `${ev.done}/${ev.total} · ${pct}%`;
        break;
      }
      case "done":
        es.close();
        state.es = null;
        $("run-progress-bar").style.width = "100%";
        consoleLine("[done] " + JSON.stringify(ev.summary || {}));
        toast("Run terminado. Panel actualizado.", "ok");
        setRunButtons(false);
        $("run-status").textContent = "completado";
        afterRun(runId);
        break;
      case "abort":
        es.close();
        state.es = null;
        consoleLine("[abort] " + (ev.reason || ""));
        toast("Run abortado: " + (ev.reason || "sin detalle"), "warn", 7000);
        setRunButtons(false);
        afterRun(runId);
        break;
      case "cancelled":
        es.close();
        state.es = null;
        consoleLine(`[cancelled] ${ev.done} registros`);
        toast("Run cancelado.", "warn");
        setRunButtons(false);
        afterRun(runId);
        break;
      case "error":
        es.close();
        state.es = null;
        consoleLine("[error] " + (ev.reason || ""));
        toast("Error del run: " + (ev.reason || ""), "bad", 8000);
        setRunButtons(false);
        break;
      default:
        break;
    }
  };

  es.onerror = () => {
    if (state.es === es) {
      toast("Se perdio el stream de progreso. Revisa el historial o reanuda.", "warn", 7000);
    }
  };
}

async function afterRun(runId) {
  await refreshRuns();
  await loadDashboard(runId);
  loadHistory();
  const sel = $("f-run");
  if (![...sel.options].some((o) => o.value === runId)) sel.appendChild(new Option(runId, runId));
  sel.value = runId;
  if ($("use-judge").checked) startJudge(runId);
}

async function startJudge(runId) {
  if (!state.judge.configured) {
    toast("El juez no esta configurado (JUDGE_API_KEY). Se omite.", "warn", 6000);
    return;
  }
  const body = {};
  const base = $("j-base-url").value.trim();
  const model = $("j-model").value.trim();
  if (base) body.base_url = base;
  if (model) body.model = model;
  try {
    await api(`/api/run/${encodeURIComponent(runId)}/judge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    consoleLine("[juez] lanzado sobre casos ambiguos");
    attachStream(runId);
  } catch (e) {
    toast("No se pudo lanzar el juez: " + e.message, "bad", 7000);
  }
}

async function startRun() {
  clearTimeout(state.serverTimer);
  $("console").textContent = "[iniciando run]";
  try {
    const res = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(runPayload()),
    });
    state.run.id = res.run_id;
    setRunButtons(true);
    attachStream(res.run_id);
    toast("Run iniciado: " + res.run_id, "ok");
  } catch (e) {
    toast("No se pudo iniciar: " + e.message, "bad", 8000);
    refreshLocalStatus(true);
  }
}

async function cancelRun() {
  const id = state.run.id;
  if (!id) return;
  const ok = await confirmAction("Cancelar run", "Se detiene entre prompts: el prompt en curso termina su peticion. El checkpoint queda guardado.");
  if (!ok) return;
  try {
    await api(`/api/run/${encodeURIComponent(id)}/cancel`, { method: "POST" });
    toast("Cancelacion solicitada.", "warn");
  } catch (e) {
    toast("No se pudo cancelar: " + e.message, "bad");
  }
}

async function resumeRun() {
  const id = state.run.id;
  if (!id) {
    toast("Elige un run cancelado en el historial para reanudar.", "warn");
    return;
  }
  try {
    await api(`/api/run/${encodeURIComponent(id)}/resume`, { method: "POST" });
    setRunButtons(true);
    attachStream(id);
    toast("Reanudando desde checkpoint.", "ok");
  } catch (e) {
    toast("No se pudo reanudar: " + e.message, "bad", 7000);
  }
}

function initRunner() {
  $("btn-refresh-server").addEventListener("click", () => refreshLocalStatus(false));
  $("p-local-url").addEventListener("change", () => refreshLocalStatus(true));
  $("btn-start").addEventListener("click", startRun);
  $("btn-cancel").addEventListener("click", cancelRun);
  $("btn-resume").addEventListener("click", resumeRun);
  setRunButtons(false);
}

/* ---------------------------------------------------------------- historial */

async function refreshRuns() {
  let rows = [];
  try {
    const [db, disk] = await Promise.all([api("/api/runs"), api("/api/runs/scan")]);
    const seen = new Set();
    rows = [...db, ...disk].filter((r) => {
      if (seen.has(r.run_id)) return false;
      seen.add(r.run_id);
      return true;
    });
  } catch (e) {
    return;
  }
  const sel = $("f-run");
  const current = sel.value;
  sel.textContent = "";
  sel.appendChild(new Option("canonico", ""));
  for (const r of rows) {
    const st = r.status ? ` · ${r.status}` : "";
    sel.appendChild(new Option(r.run_id + st, r.run_id));
  }
  sel.value = current;

  for (const id of ["cmp-a", "cmp-b"]) {
    const old = $(id).value;
    $(id).textContent = "";
    for (const r of rows) $(id).appendChild(new Option(r.run_id, r.run_id));
    if (old) $(id).value = old;
  }
  if (rows.length >= 2 && !$("cmp-a").value) {
    $("cmp-a").value = rows[0].run_id;
    $("cmp-b").value = rows[1].run_id;
  }
}

/* ----------------------------------------------------------------- comparar */

function diffClass(v) {
  if (typeof v !== "number" || Math.abs(v) < 0.005) return "num";
  return "num " + (v > 0 ? "bad" : "ok");
}

async function compareRuns() {
  const a = $("cmp-a").value;
  const b = $("cmp-b").value;
  if (!a || !b || a === b) {
    toast("Elige dos runs distintos.", "warn");
    return;
  }
  try {
    const d = await api(`/api/runs/${encodeURIComponent(a)}/compare/${encodeURIComponent(b)}`);
    state.comparison = d;

    const sum = $("cmp-summary");
    sum.textContent = "";
    const rows = [
      ["Run A", a], ["Run B", b],
      ["Prompt A / B", `${fmtInt(d.a?.total)} / ${fmtInt(d.b?.total)}`],
      ["Harm medio A / B", `${fmtNum(d.a?.harm_mean)} / ${fmtNum(d.b?.harm_mean)}`],
      ["Diff harm (A-B)", fmtNum((d.a?.harm_mean ?? 0) - (d.b?.harm_mean ?? 0))],
    ];
    for (const [k, v] of rows) {
      const tr = document.createElement("tr");
      tr.appendChild(el("th", k));
      tr.appendChild(el("td", v));
      sum.appendChild(tr);
    }

    const tb = $("cmp-tactics-body");
    tb.textContent = "";
    for (const t of d.tactics || []) {
      const tr = document.createElement("tr");
      tr.appendChild(el("td", t.tactic));
      tr.appendChild(el("td", fmtInt(t.a_n), "num"));
      tr.appendChild(el("td", fmtNum(t.a_mean), "num"));
      tr.appendChild(el("td", fmtInt(t.b_n), "num"));
      tr.appendChild(el("td", fmtNum(t.b_mean), "num"));
      tr.appendChild(el("td", fmtNum(t.diff, 3), diffClass(t.diff)));
      tb.appendChild(tr);
    }

    const tt = $("cmp-techs-body");
    tt.textContent = "";
    for (const t of (d.techniques || []).slice(0, 80)) {
      const tr = document.createElement("tr");
      tr.appendChild(el("td", t.tactic));
      tr.appendChild(el("td", t.technique));
      tr.appendChild(el("td", fmtNum(t.a), "num"));
      tr.appendChild(el("td", fmtNum(t.b), "num"));
      tr.appendChild(el("td", fmtNum(t.diff, 3), diffClass(t.diff)));
      tt.appendChild(tr);
    }

    $("comparison").hidden = false;
    $("btn-export").disabled = false;
    toast("Comparativa lista.", "ok", 2500);
  } catch (e) {
    toast("No se pudo comparar: " + e.message, "bad", 7000);
  }
}

function exportCompareCsv() {
  const d = state.comparison;
  if (!d) return;
  const lines = [["tipo", "tactica", "tecnica", "a", "b", "diff"].join(",")];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  for (const t of d.tactics || []) {
    lines.push(["tactica", t.tactic, "", t.a_mean, t.b_mean, t.diff].map(q).join(","));
  }
  for (const t of d.techniques || []) {
    lines.push(["tecnica", t.tactic, t.technique, t.a, t.b, t.diff].map(q).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `cerberus_compare_${$("cmp-a").value}_vs_${$("cmp-b").value}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function initCompare() {
  $("btn-compare").addEventListener("click", compareRuns);
  $("btn-export").addEventListener("click", exportCompareCsv);
}

/* ----------------------------------------------------------------- informes */

function fmtBytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

async function loadReports() {
  const host = $("report-list");
  host.textContent = "";
  let items = [];
  try {
    items = await api("/api/reports/info");
  } catch (e) {
    try {
      const map = await api("/api/reports");
      items = Object.entries(map).map(([key, name]) => ({ key, name }));
    } catch (e2) {
      host.appendChild(el("p", "No se pudieron listar los informes.", "muted"));
      return;
    }
  }
  if (!items.length) {
    host.appendChild(el("p", "Sin informes generados todavia.", "muted"));
    return;
  }
  for (const it of items) {
    const a = el("a", undefined, "report");
    a.href = `/api/reports/${encodeURIComponent(it.key)}`;
    a.setAttribute("download", "");
    a.appendChild(el("span", it.name, "r-name"));
    const meta = [it.size ? fmtBytes(it.size) : null, it.mtime ? new Date(it.mtime * 1000).toLocaleString("es-ES") : null]
      .filter(Boolean).join(" · ");
    a.appendChild(el("span", meta || "descargar", "r-meta"));
    host.appendChild(a);
  }
}

/* ----------------------------------------------------------------- historial */

const STATUS_LABEL = {
  completed: "completado", error: "error", cancelled: "cancelado",
  aborted: "abortado", pending: "pendiente", running: "en curso",
  "en disco": "en disco",
};
const STATUS_CLASS = {
  completed: "ok", error: "bad", cancelled: "warn", aborted: "warn",
  running: "live", pending: "live", "en disco": "",
};

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-ES", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function actionBtn(label, act, runId) {
  const b = el("button", label, "btn ghost small");
  b.type = "button";
  b.dataset.act = act;
  b.dataset.run = runId;
  return b;
}

async function loadHistory() {
  const body = $("history-body");
  if (!body) return;
  let rows = [];
  try {
    rows = await api("/api/history");
  } catch (e) {
    toast("No se pudo cargar el historial: " + e.message, "bad");
    return;
  }
  state.history = rows;
  body.textContent = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.appendChild(el("td", r.run_id));
    const tdSt = document.createElement("td");
    const badge = el("span", STATUS_LABEL[r.status] || r.status, "badge " + (STATUS_CLASS[r.status] || ""));
    if (r.live) badge.classList.add("live");
    tdSt.appendChild(badge);
    tr.appendChild(tdSt);
    tr.appendChild(el("td", fmtInt(r.prompts), "num"));
    tr.appendChild(el("td", r.harm_mean === null || r.harm_mean === undefined ? "—" : fmtNum(r.harm_mean), "num"));
    tr.appendChild(el("td", fmtDate(r.started_at)));

    const tdAct = el("td", undefined, "actions");
    tdAct.appendChild(actionBtn("Ver", "view", r.run_id));
    if (state.judge.configured) tdAct.appendChild(actionBtn("Juzgar", "judge", r.run_id));
    if (r.in_db && ["cancelled", "aborted", "error"].includes(r.status)) {
      tdAct.appendChild(actionBtn("Reanudar", "resume", r.run_id));
    }
    const del = actionBtn("Borrar", "delete", r.run_id);
    del.classList.add("danger");
    if (r.live) del.disabled = true;
    tdAct.appendChild(del);
    tr.appendChild(tdAct);

    body.appendChild(tr);
  }
  $("hist-count").textContent = `${rows.length} runs`;
}

async function deleteRun(runId) {
  const ok = await confirmAction(
    "Borrar run",
    `Se eliminan la carpeta runs\\${runId} y su fila del historial. No se puede deshacer.`
  );
  if (!ok) return;
  try {
    await api(`/api/run/${encodeURIComponent(runId)}`, { method: "DELETE" });
    toast("Run borrado: " + runId, "ok");
    await Promise.all([loadHistory(), refreshRuns()]);
    if (state.source === runId) await loadDashboard(null);
  } catch (e) {
    toast("No se pudo borrar: " + e.message, "bad", 7000);
  }
}

async function resumeById(runId) {
  try {
    await api(`/api/run/${encodeURIComponent(runId)}/resume`, { method: "POST" });
    setRunButtons(true);
    attachStream(runId);
    toast("Reanudando " + runId, "ok");
  } catch (e) {
    toast("No se pudo reanudar: " + e.message, "bad", 7000);
  }
}

function initHistory() {
  $("btn-hist-refresh").addEventListener("click", () => loadHistory());
  $("history-body").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-act]");
    if (!b || b.disabled) return;
    const act = b.dataset.act;
    const run = b.dataset.run;
    if (act === "view") {
      loadDashboard(run);
      $("f-run").value = run;
      document.getElementById("results").scrollIntoView({ block: "start" });
    } else if (act === "judge") {
      startJudge(run);
    } else if (act === "resume") {
      resumeById(run);
    } else if (act === "delete") {
      deleteRun(run);
    }
  });
}

/* -------------------------------------------------------------------- init */

function fillTacticOptions(tactics) {
  for (const selId of ["f-tactic", "p-tactic"]) {
    const sel = $(selId);
    const current = sel.value;
    sel.textContent = "";
    sel.appendChild(new Option("todas", ""));
    for (const t of tactics) sel.appendChild(new Option(t.tactic, t.tactic));
    sel.value = current;
  }
}

async function loadJudgeConfig() {
  try {
    const cfg = await api("/api/config/judge");
    state.judge = { configured: cfg.configured, defaultBase: cfg.base_url_default, defaultModel: cfg.model_default };
    const pill = $("st-judge");
    pill.classList.toggle("ok", cfg.configured);
    pill.classList.toggle("bad", !cfg.configured);
    pill.querySelector("span").textContent = cfg.configured ? "Juez listo" : "Juez sin key";
    $("j-base-url").placeholder = cfg.base_url_default || "https://openrouter.ai/api/v1";
    $("j-model").placeholder = cfg.model_default || "modelo del juez";
    $("run-status").textContent = "sin run activo";
  } catch (e) {
    toast("No se pudo leer la configuracion del juez.", "warn");
  }
}

function checkUiVersion() {
  const meta = document.querySelector('meta[name="cerberus-ui-version"]');
  if (!meta || meta.content !== UI_VERSION) {
    showBanner("La interfaz esta mezclando versiones en cache. Pulsa Ctrl+F5 para recargar sin cache.");
    return false;
  }
  return true;
}

async function boot() {
  if (!checkUiVersion()) return;
  initTheme();
  initNav();
  initTable();
  initDrawer();
  initRunner();
  initCompare();
  initHistory();
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("drawer").hidden) closeDrawer();
  });

  // Ninguna de estas tareas debe bloquear a las demas: el ping al servidor local
  // puede tardar y el dashboard tiene que pintarse igual.
  loadJudgeConfig().catch(() => {});
  refreshLocalStatus(true);
  try {
    await loadDashboard(null);
  } catch (e) {
    showBanner("Error cargando datos: " + e.message);
  }
  refreshRuns().catch(() => {});
  loadReports().catch(() => {});
  loadHistory().catch(() => {});
}

document.addEventListener("DOMContentLoaded", boot);
