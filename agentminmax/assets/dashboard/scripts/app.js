const fmt = new Intl.NumberFormat("en-US");

let observation = null;
let sources = [];
let selectedSession = null;
let selectedRun = null;
let sessionTable = null;
let benchmarkTable = null;
let charts = {};
let detailActionSequence = 0;
const sessionDetails = new Map();
const benchmarkDetails = new Map();
const detailActionPayloads = new Map();
const metricGroupVisualizers = {
  bars: renderMetricBars,
  cards: renderMetricCards,
  histogram: renderMetricHistogram
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh-all").addEventListener("click", refreshAllSources);
  document.getElementById("detail-modal-close").addEventListener("click", hideDetailModal);
  document.getElementById("detail-modal").addEventListener("click", (event) => {
    if (event.target.dataset.detailClose) hideDetailModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideDetailModal();
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-detail-action-id]");
    if (!button) return;
    const payload = detailActionPayloads.get(button.dataset.detailActionId);
    if (payload) showDetailModal(payload);
  });
  loadDashboard();
  window.addEventListener("resize", () => Object.values(charts).forEach((chart) => chart.resize()));
});

async function loadDashboard() {
  setStatus("Loading");
  try {
    observation = await fetchJson("/api/observation").catch(() => fetchJson("observations.json"));
    const sourcePayload = await fetchJson("/api/sources").catch(() => ({ sources: observation.sources || [] }));
    sources = sourcePayload.sources || [];
    renderAll();
    setStatus("Loaded");
  } catch (error) {
    console.error(error);
    setStatus("Error");
  }
}

function renderAll() {
  detailActionPayloads.clear();
  renderMetrics(observation.summary);
  renderSourceList();
  renderBenchmarkSources();
  renderTables();
  renderSessionAnalysis(selectedSession);
  renderBenchmarkAnalysis(selectedRun);
}

function renderMetrics(summary) {
  const metrics = [
    ["Sessions", summary.session_count],
    ["Tokens", summary.total_tokens],
    ["Tool Calls", summary.total_tool_calls],
    ["Lines Changed", summary.total_lines_changed],
    ["Bench Complete", pct(summary.benchmark_completion_rate)],
    ["Avg Quality", pct(summary.average_quality_score)]
  ];
  document.getElementById("metric-grid").innerHTML = metrics.map(([label, value]) => `
    <article class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${typeof value === "number" ? fmt.format(value) : value}</strong>
    </article>
  `).join("");
}

function renderSourceList() {
  const list = document.getElementById("source-list");
  if (!sources.length) {
    list.innerHTML = '<p class="empty">No sources configured. Static observations are still available.</p>';
    return;
  }
  list.innerHTML = sources.map((source) => sourceCardHtml(source, sourceSessionSummary(source.id))).join("");
  list.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => triggerSource(button.dataset.sourceId, button.dataset.action));
  });
}

function renderBenchmarkSources() {
  const list = document.getElementById("benchmark-source-list");
  const observedNames = observedBenchmarkNames();
  if (!sources.length && !observedNames.length) {
    list.innerHTML = '<p class="empty">No benchmark context is available yet. Ingest sessions with benchmark task results to populate this area.</p>';
    return;
  }

  const sourceItems = sources.map((source) => {
    const summary = sourceBenchmarkSummary(source.id);
    return sourceCardHtml(source, summary);
  });
  const observedItem = observedNames.length ? `
    <div class="source-item">
      <div class="source-main">
        <strong>Observed Benchmarks</strong>
        <span>${observedNames.map((name) => escapeHtml(name)).join(", ")}</span>
      </div>
      <div class="source-meta">${fmt.format(observedNames.length)} suites</div>
      <div class="source-actions"></div>
    </div>
  ` : "";
  list.innerHTML = [...sourceItems, observedItem].join("");
  list.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => triggerSource(button.dataset.sourceId, button.dataset.action));
  });
}

function sourceCardHtml(source, summary) {
  return `
    <div class="source-item" data-source-id="${escapeHtml(source.id)}">
      <div class="source-main">
        <strong>${escapeHtml(source.label || source.id)}</strong>
        <span>${escapeHtml(source.path || (source.command || []).join(" ") || "no path")}</span>
      </div>
      <div class="source-meta">${escapeHtml(summary)} · ${escapeHtml(source.last_status || "never")}</div>
      <div class="source-actions">
        <button class="tool-button" data-action="refresh" data-source-id="${escapeHtml(source.id)}">Refresh</button>
        <button class="tool-button" data-action="run" data-source-id="${escapeHtml(source.id)}">Run</button>
      </div>
    </div>
  `;
}

function renderTables() {
  renderBenchmarkTable();
  renderSessionTable(filteredSessions());
}

function renderBenchmarkTable() {
  const runRows = (observation.benchmark_runs || []).map((run) => ({
    key: runKey(run),
    _run: run,
    source_id: run.source_id,
    source: sourceLabel(run.source_id),
    benchmark: run.benchmark,
    run_id: run.run_id,
    task_count: run.task_count,
    session_count: run.session_count,
    completion_rate: run.completion_rate,
    average_quality_score: run.average_quality_score,
    total_tokens: run.total_tokens,
    total_tool_calls: run.total_tool_calls
  }));

  if (benchmarkTable) {
    benchmarkTable.setData(runRows);
  } else {
    benchmarkTable = new Tabulator("#benchmark-table", {
      data: runRows,
      layout: "fitColumns",
      height: "260px",
      selectableRows: 1,
      placeholder: "No benchmark runs in this observation.",
      columns: [
        { title: "Source", field: "source", headerFilter: true },
        { title: "Benchmark", field: "benchmark", headerFilter: true },
        { title: "Run", field: "run_id" },
        { title: "Tasks", field: "task_count", hozAlign: "right" },
        { title: "Sessions", field: "session_count", hozAlign: "right" },
        { title: "Complete", field: "completion_rate", formatter: percentFormatter, hozAlign: "right" },
        { title: "Quality", field: "average_quality_score", formatter: percentFormatter, hozAlign: "right" },
        { title: "Tokens", field: "total_tokens", formatter: numberFormatter, hozAlign: "right" }
      ]
    });
    benchmarkTable.on("rowClick", selectBenchmarkRun);
  }
}

function renderSessionTable(sessions) {
  const rows = sessions.map((session) => ({
    _session: session,
    session_id: session.session_id,
    source_id: session.source_id,
    source: sourceLabel(session.source_id),
    model: session.model.name,
    size: session.model.parameters.declared_size || session.model.parameters.size || "unknown",
    tokens: session.tokens.input + session.tokens.output,
    tools: sumValues(session.tool_calls),
    duration: session.duration_seconds,
    quality: averageQuality(session.benchmarks),
    lines: session.code.lines_added + session.code.lines_deleted,
    grain: session.complexity.recommended_grain
  }));

  if (sessionTable) {
    sessionTable.setData(rows);
    return;
  }
  sessionTable = new Tabulator("#session-table", {
    data: rows,
    layout: "fitColumns",
    height: "320px",
    placeholder: "No sessions match the current filter.",
    columns: [
      { title: "Session", field: "session_id", headerFilter: true, widthGrow: 2 },
      { title: "Source", field: "source", headerFilter: true },
      { title: "Model", field: "model", headerFilter: true },
      { title: "Size", field: "size" },
      { title: "Tokens", field: "tokens", formatter: numberFormatter, hozAlign: "right" },
      { title: "Tools", field: "tools", hozAlign: "right" },
      { title: "Duration", field: "duration", formatter: secondsFormatter, hozAlign: "right" },
      { title: "Quality", field: "quality", formatter: percentFormatter, hozAlign: "right" },
      { title: "Lines", field: "lines", formatter: numberFormatter, hozAlign: "right" },
      { title: "Grain", field: "grain" }
    ]
  });
  sessionTable.on("rowClick", selectSession);
}

async function selectSession(_event, row) {
  const summary = row.getData()._session;
  selectedSession = summary;
  renderSessionAnalysis(summary);
  setAnalysisLoading("session-analysis", true);
  setStatus("Loading session");
  try {
    const detail = await loadSessionDetail(summary);
    if (selectedSession && selectedSession.session_id === summary.session_id) {
      selectedSession = detail;
      renderSessionAnalysis(detail);
      setStatus("Loaded");
    }
  } catch (error) {
    console.error(error);
    setStatus("Session detail unavailable");
  } finally {
    if (selectedSession && selectedSession.session_id === summary.session_id) {
      setAnalysisLoading("session-analysis", false);
    }
  }
}

async function selectBenchmarkRun(_event, row) {
  const summary = row.getData()._run;
  selectedRun = summary;
  renderBenchmarkAnalysis(summary);
  renderSessionTable(filteredSessions());
  setAnalysisLoading("benchmark-analysis", true);
  setStatus("Loading benchmark");
  try {
    const detail = await loadBenchmarkDetail(summary);
    if (selectedRun && runKey(selectedRun) === runKey(summary)) {
      selectedRun = detail;
      renderBenchmarkAnalysis(detail);
      renderSessionTable(filteredSessions());
      setStatus("Loaded");
    }
  } catch (error) {
    console.error(error);
    setStatus("Benchmark detail unavailable");
  } finally {
    if (selectedRun && runKey(selectedRun) === runKey(summary)) {
      setAnalysisLoading("benchmark-analysis", false);
    }
  }
}

function renderSessionAnalysis(session) {
  const panel = document.getElementById("session-analysis");
  setPanelVisibility(panel, Boolean(session));
  if (!session) return;

  const model = session.model || {};

  document.getElementById("session-analysis-context").textContent = `${session.session_id} · ${sourceLabel(session.source_id)}`;
  document.getElementById("session-overview-metrics").innerHTML = metricItems([
    ["Agent", session.agent || "unknown"],
    ["Model", model.name || "unknown"],
    ["Provider", model.provider || "unknown"],
    ["Status", session.status || "unknown"]
  ]);
  document.getElementById("session-metric-events").innerHTML = renderMetricEvents(session.metric_events || []);
  document.getElementById("session-metric-group-cards").innerHTML = renderMetricGroupCards(session.metric_groups || []);
  document.getElementById("session-related-benchmarks").innerHTML = relatedBenchmarkList(session);
  document.getElementById("session-log-list").innerHTML = logTimeline(session);
  document.getElementById("session-trace-links").innerHTML = renderTraceLinks(session.trace, `Session ${session.session_id}`);
  AgentMinMaxPerfetto.render({
    frameId: "session-perfetto-frame",
    statusId: "session-perfetto-status",
    trace: session.trace,
    title: `Session ${session.session_id}`
  });
  renderSessionTokenGrowthChart(session);
}

function renderBenchmarkAnalysis(run) {
  const panel = document.getElementById("benchmark-analysis");
  setPanelVisibility(panel, Boolean(run));
  if (!run) return;

  document.getElementById("benchmark-analysis-context").textContent = `${run.benchmark} · ${run.run_id || "unassigned"}`;
  document.getElementById("benchmark-metric-group-cards").innerHTML = renderMetricGroupCards(run.metric_groups || []);
  document.getElementById("benchmark-session-list").innerHTML = sessionChipList(benchmarkSessions(run));
  document.getElementById("benchmark-task-results").innerHTML = benchmarkTaskList(run);
  document.getElementById("benchmark-trace-links").innerHTML = renderTraceLinks(run.trace, `${run.benchmark} · ${run.run_id || "unassigned"}`);
  AgentMinMaxPerfetto.render({
    frameId: "benchmark-perfetto-frame",
    statusId: "benchmark-perfetto-status",
    trace: run.trace,
    title: `${run.benchmark} · ${run.run_id || "unassigned"}`
  });
}

function setPanelVisibility(panel, visible) {
  panel.classList.toggle("is-hidden", !visible);
  panel.setAttribute("aria-hidden", visible ? "false" : "true");
}

function setAnalysisLoading(panelId, loading) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  panel.querySelectorAll(".analysis-card").forEach((card) => {
    card.classList.toggle("is-loading", loading);
    card.setAttribute("aria-busy", loading ? "true" : "false");
  });
}

function metricItems(items) {
  return items.map(([label, value]) => `
    <div class="detail-metric">
      <div class="metric-main">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
      <div class="metric-actions">
        ${detailActionButton(genericMetricDetailPayload(label, value))}
      </div>
    </div>
  `).join("");
}

function renderMetricGroupCards(groups) {
  if (!groups.length) {
    return `<article class="analysis-card metric-group-card wide">
      <h3>Metrics</h3>
      <p class="empty">No grouped metrics captured.</p>
    </article>`;
  }
  return groups.map((group) => `
    <article class="analysis-card metric-group-card${(group.metrics || []).length > 4 ? " wide" : ""}">
      <div class="metric-group-head">
        <h3>${escapeHtml(group.label || group.group_id)}</h3>
        <span>${fmt.format((group.metrics || []).length)} metrics</span>
        <div class="metric-group-actions">
          ${detailActionButton(groupDetailPayload(group))}
        </div>
      </div>
      ${metricGroupDisplayHtml(group)}
    </article>
  `).join("");
}

function metricGroupDisplayHtml(group) {
  const config = metricGroupVisualConfig(group);
  const renderer = metricGroupVisualizers[config.kind] || metricGroupVisualizers.cards;
  return renderer(group.metrics || [], config, group);
}

function metricGroupVisualConfig(group) {
  return Object.assign({ kind: "cards" }, group.display || {});
}

function renderMetricCards(metrics) {
  return `<div class="detail-metrics">
    ${metrics.map((metric) => {
      return `
        <div class="detail-metric" title="${escapeHtml(metric.description || "")}">
          <div class="metric-main">
            <span>${escapeHtml(metric.label || metric.metric_id)}</span>
            <strong>${escapeHtml(metricValueText(metric))}</strong>
          </div>
          <div class="metric-actions">
            ${detailActionButton(metricDetailPayload(metric))}
          </div>
        </div>
      `;
    }).join("")}
  </div>`;
}

function clampPercent(value, minValue = 2) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(Math.min(value, 100), minValue);
}

function renderMetricBars(metrics, config = {}) {
  const numeric = metrics.filter((metric) => typeof metric.value === "number");
  if (!numeric.length) return renderMetricCards(metrics);
  const maxValue = metricBarMaxValue(numeric, config);
  return `<div class="metric-bars">
    ${metrics.map((metric) => metricBarRow(metric, maxValue, config)).join("")}
  </div>`;
}

function metricBarRow(metric, maxValue, config = {}) {
  const label = metric.label || metric.metric_id;
  const description = metric.description || "";
  if (typeof metric.value !== "number") {
    return `
      <div class="metric-bar-row text" title="${escapeHtml(description)}">
        <div class="metric-bar-main">
          <span>${escapeHtml(label)}</span>
          <strong class="metric-bar-meta">${escapeHtml(metricValueText(metric))}</strong>
        </div>
        <div class="metric-actions">
          ${detailActionButton(metricDetailPayload(metric))}
        </div>
      </div>
    `;
  }
  const magnitude = metricBarMagnitude(metric, config);
  const width = clampPercent((magnitude / maxValue) * 100, config.min_percent ?? 2);
  return `
    <div class="metric-bar-row" title="${escapeHtml(description)}">
      <div class="metric-bar-main">
        <div class="metric-bar-head">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(metricValueText(metric))}</strong>
        </div>
        <div class="metric-bar-track">
          <div class="metric-bar-fill ${escapeHtml(metricBarKind(metric))}" style="width: ${width}%"></div>
        </div>
      </div>
      <div class="metric-actions">
        ${detailActionButton(metricDetailPayload(metric))}
      </div>
    </div>
  `;
}

function metricBarMaxValue(metrics, config = {}) {
  if (typeof config.max === "number" && config.max > 0) return config.max;
  return Math.max(...metrics.map((metric) => metricBarMagnitude(metric, config)), 1);
}

function metricBarMagnitude(metric, config = {}) {
  const value = Math.abs(Number(metric.value) || 0);
  if (metricBarKind(metric) === "bounded" && config.value_scale !== "raw") return value * 100;
  return value;
}

function metricBarKind(metric) {
  if (["ratio", "score", "variance"].includes(metric.unit) && Math.abs(Number(metric.value) || 0) <= 1) {
    return "bounded";
  }
  return "magnitude";
}

function renderMetricHistogram(metrics) {
  const numeric = metrics.filter((metric) => typeof metric.value === "number");
  if (!numeric.length) return renderMetricCards(metrics);
  const maxValue = Math.max(...numeric.map((metric) => Math.abs(metric.value)), 1);
  return `<div class="metric-histogram">
    ${numeric.map((metric) => {
      const width = Math.max(Math.abs(metric.value) / maxValue * 100, 2);
      return `
        <div class="metric-histogram-row" title="${escapeHtml(metric.description || "")}">
          <span>${escapeHtml(metric.label || metric.metric_id)}</span>
          <div class="metric-histogram-track">
            <div class="metric-histogram-bar" style="width: ${width}%"></div>
          </div>
          <strong>${escapeHtml(metricValueText(metric))}</strong>
          <div class="metric-actions">
            ${detailActionButton(metricDetailPayload(metric))}
          </div>
        </div>
      `;
    }).join("")}
  </div>`;
}

function renderMetricEvents(events) {
  if (!events.length) return '<p class="empty">Metric events are available after session detail loads.</p>';
  return events.map((event) => {
    return `
      <div class="metric-event">
        <div class="metric-main">
          <strong>${escapeHtml(event.name || "metric.event")}</strong>
          <code>${escapeHtml(metricEventValueText(event))}</code>
        </div>
        <div class="metric-actions">
          ${detailActionButton(eventDetailPayload(event))}
        </div>
      </div>
    `;
  }).join("");
}

function metricEventValueText(event) {
  const unit = event.unit && event.unit !== "count" ? ` ${event.unit}` : "";
  const value = event.value;
  if (typeof value === "number") {
    if (Number.isInteger(value)) return `${fmt.format(value)}${unit}`;
    return `${fmt.format(Math.round(value * 10000) / 10000)}${unit}`;
  }
  return `${value ?? "unknown"}${unit}`;
}

function metricValueText(metric) {
  const value = metric.value;
  const unit = metric.unit && !["count", "class"].includes(metric.unit) ? ` ${metric.unit}` : "";
  if (value === "unknown") return "unknown";
  if (typeof value === "number") {
    if (metric.unit === "ratio") return pct(value);
    if (Number.isInteger(value)) return `${fmt.format(value)}${unit}`;
    return `${fmt.format(Math.round(value * 10000) / 10000)}${unit}`;
  }
  return `${value ?? "unknown"}${unit}`;
}

function detailActionButton(payload) {
  const id = `detail-${++detailActionSequence}`;
  detailActionPayloads.set(id, payload);
  const label = `View details for ${payload.title || "metric"}`;
  return `<div class="metric-action-box">
    <button class="detail-action-button" type="button" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" data-detail-action-id="${escapeHtml(id)}">View</button>
  </div>`;
}

function groupDetailPayload(group) {
  return {
    title: group.label || group.group_id,
    subtitle: `Metric group · ${fmt.format((group.metrics || []).length)} metrics`,
    rows: [
      ["Group ID", group.group_id || "unknown"],
      ["Display", (group.display || {}).kind || "cards"],
      ["Metrics", (group.metrics || []).map((metric) => metric.metric_id).join(", ") || "none"]
    ]
  };
}

function metricDetailPayload(metric) {
  return {
    title: metric.label || metric.metric_id,
    subtitle: `Metric · ${metric.metric_id || "unknown"}`,
    rows: [
      ["Value", metricValueText(metric)],
      ["Unit", metric.unit || "count"],
      ["Description", metric.description || "No description captured."],
      ["Labels", metricLabelsText(metric.labels)],
      ["Inputs", (metric.inputs || []).join(", ") || "none"],
      ["Formula", metric.formula || "direct event value"]
    ]
  };
}

function metricLabelsText(labels) {
  const entries = Object.entries(labels || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!entries.length) return "none";
  return entries.map(([key, value]) => `${key}=${value}`).join(", ");
}

function genericMetricDetailPayload(label, value) {
  return {
    title: label || "Metric",
    subtitle: "Metric",
    rows: [
      ["Value", value ?? "unknown"],
      ["Inputs", "derived from the current selected observation"],
      ["Formula", "direct dashboard field"]
    ]
  };
}

function eventDetailPayload(event) {
  const labels = Object.entries(event.labels || {}).map(([key, value]) => `${key}=${value}`).join(", ");
  const meta = [event.category, event.timestamp, labels].filter(Boolean).join(" · ");
  return {
    title: event.name || "metric.event",
    subtitle: `Event · ${event.category || "general"}`,
    rows: [
      ["Value", metricEventValueText(event)],
      ["Unit", event.unit || "count"],
      ["Category", event.category || "general"],
      ["Timestamp", event.timestamp || "none"],
      ["Labels", labels || "none"],
      ["Summary", meta || "No additional metadata captured."]
    ]
  };
}

function showDetailModal(payload) {
  document.getElementById("detail-modal-title").textContent = payload.title || "Details";
  document.getElementById("detail-modal-subtitle").textContent = payload.subtitle || "";
  document.getElementById("detail-modal-body").innerHTML = detailRowsHtml(payload.rows || []);
  document.getElementById("detail-modal").classList.remove("is-hidden");
}

function hideDetailModal() {
  document.getElementById("detail-modal").classList.add("is-hidden");
}

function detailRowsHtml(rows) {
  return rows.map(([label, value]) => `
    <div class="detail-modal-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function relatedBenchmarkList(session) {
  const groups = new Map();
  (session.benchmarks || []).forEach((result) => {
    const key = result.benchmark;
    if (!groups.has(key)) {
      groups.set(key, {
        benchmark: result.benchmark,
        taskIds: new Set()
      });
    }
    groups.get(key).taskIds.add(result.task_id);
  });

  const related = Array.from(groups.values()).sort((left, right) => left.benchmark.localeCompare(right.benchmark));
  if (!related.length) return '<p class="empty">No related benchmarks captured.</p>';
  return related.map((item) => `
    <div class="detail-chip">
      <span>${escapeHtml(sourceLabel(session.source_id))} · ${escapeHtml(sessionRunId(session))} · ${fmt.format(item.taskIds.size)} tasks</span>
      <strong>${escapeHtml(item.benchmark)}</strong>
    </div>
  `).join("");
}

function benchmarkResultList(results, includeSession = false) {
  if (!results.length) return '<p class="empty">No benchmark task results captured.</p>';
  return `<div class="detail-task-list">${results.map((result) => {
    const status = result.completed ? "complete" : "incomplete";
    const title = includeSession ? `${result.session_id} / ${result.task_id}` : result.task_id;
    return `<div class="detail-task ${status}">
      <div>
        <span>${escapeHtml(result.benchmark)}</span>
        <strong>${escapeHtml(title)}</strong>
      </div>
      <div>
        <span>tests</span>
        <strong>${fmt.format(result.tests_passed || 0)} / ${fmt.format(result.tests_total || 0)}</strong>
      </div>
      <div>
        <span>quality</span>
        <strong class="status">${pct(result.quality_score)}</strong>
      </div>
    </div>`;
  }).join("")}</div>`;
}

function logTimeline(session) {
  const entries = timelineEntries(session);
  if (!entries.length) return '<p class="empty">No logs captured.</p>';
  return entries.map((entry) => {
    const detail = entry.detail ? `<div class="log-detail">${escapeHtml(shortLogText(entry.detail))}</div>` : "";
    const output = entry.output ? `<pre class="log-output">${escapeHtml(shortLogText(entry.output, 2200))}</pre>` : "";
    return `
    <div class="log-entry ${escapeHtml(entry.kind)}${entry.status === "error" ? " error" : ""}">
      <div class="log-time">${escapeHtml(entry.time)}</div>
      <div class="log-rail"><span class="log-dot"></span></div>
      <div class="log-body">
        <div class="log-row">
          <div class="log-title">
            <strong>${escapeHtml(entry.title)}</strong>
            <span>${escapeHtml(entry.subtitle)}</span>
          </div>
          ${tokenCostHtml(entry.tokens)}
        </div>
        ${detail}
        ${output}
      </div>
    </div>
  `;
  }).join("");
}

function timelineEntries(session) {
  const traceEvents = (session.trace_events || [])
    .slice()
    .sort((left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp));
  const entries = [];
  let currentTokens = null;

  traceEvents.forEach((event) => {
    if (event.category === "tokens") currentTokens = event.tokens || currentTokens;
    const entry = timelineEntry(event, currentTokens);
    if (entry) entries.push(entry);
  });

  const deduped = dedupeTimelineMessages(entries);
  if (deduped.length) return deduped;

  return (session.logs || []).map((line, index) => ({
    kind: "message",
    timestampMs: index,
    time: `#${index + 1}`,
    title: "log",
    subtitle: "session log",
    detail: line,
    output: "",
    status: "unknown",
    tokens: null
  }));
}

function timelineEntry(event, currentTokens) {
  const kind = timelineKind(event);
  const ms = timestampMs(event.timestamp);
  const summary = event.summary || event.name || event.category || "event";
  const rawDetail = event.detail || "";
  const rawOutput = event.output || "";
  const detail = rawDetail && rawDetail !== rawOutput ? rawDetail : summary;
  const output = rawOutput && rawOutput !== detail ? rawOutput : "";
  const duration = event.duration_ms ? ` · ${fmt.format(event.duration_ms)}ms` : "";
  return {
    kind,
    timestampMs: ms,
    time: eventTimeLabel(event),
    title: event.name || event.category || "event",
    subtitle: `${event.category || "event"} · ${event.status || "unknown"}${duration}`,
    detail,
    output,
    status: event.status || "unknown",
    tokens: event.category === "tokens" ? event.tokens : currentTokens
  };
}

function timelineKind(event) {
  if (event.status === "error") return "error";
  if (event.lane === "MCP Calls") return "mcp";
  if (event.category === "tool") return "tool";
  if (event.category === "message") return "message";
  if (event.category === "tokens") return "tokens";
  return event.category || "event";
}

function dedupeTimelineMessages(entries) {
  const seen = new Set();
  return entries.filter((entry) => {
    if (entry.kind !== "message") return true;
    const bucket = Number.isFinite(entry.timestampMs) ? Math.floor(entry.timestampMs / 1000) : entry.time;
    const key = `${bucket}:${entry.detail || entry.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function eventTimeLabel(event) {
  const ms = timestampMs(event.timestamp);
  if (!Number.isFinite(ms)) return event.event_id || "time";
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function tokenCostHtml(tokens) {
  if (!tokens) return '<div class="log-token-chips"><span>tokens -</span></div>';
  const input = Number(tokens.input || 0);
  const output = Number(tokens.output || 0);
  const cached = Number(tokens.cached_input || 0);
  const total = Number(tokens.total || input + output);
  return `<div class="log-token-chips">
    <span>in ${fmt.format(input)}</span>
    <span>out ${fmt.format(output)}</span>
    <span>cached ${fmt.format(cached)}</span>
    <span>total ${fmt.format(total)}</span>
  </div>`;
}

function shortLogText(value, limit = 1400) {
  const text = String(value ?? "");
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}... truncated ${fmt.format(text.length - limit)} chars`;
}

function sessionChipList(sessions) {
  if (!sessions.length) return '<p class="empty">No contributing sessions found.</p>';
  return `<div class="detail-chip-list">${sessions.map((session) => `
    <div class="detail-chip">
      <span>${escapeHtml(sourceLabel(session.source_id))}</span>
      <strong>${escapeHtml(session.session_id)}</strong>
    </div>
  `).join("")}</div>`;
}

function benchmarkTaskList(run) {
  if (run.task_results) return benchmarkResultList(run.task_results, true);
  const rows = benchmarkSessions(run).flatMap((session) => {
    return (session.benchmarks || [])
      .filter((result) => result.benchmark === run.benchmark)
      .map((result) => ({ ...result, session_id: session.session_id }));
  });
  return benchmarkResultList(rows, true);
}

function renderTraceLinks(trace, title = "AgentMinMax trace") {
  if (!trace || !trace.perfetto_json) return '<p class="empty">No trace export is available.</p>';
  const traceFile = trace.perfetto_json;
  const explorerUrl = `trace.html?file=${encodeURIComponent(traceFile)}&title=${encodeURIComponent(title)}`;
  return `
    <a class="tool-button" href="${escapeHtml(explorerUrl)}" target="_blank" rel="noreferrer">Open Embedded Perfetto</a>
    <a class="tool-button" href="${escapeHtml(traceFile)}" download>Download Perfetto JSON</a>
    <span class="source-meta">${fmt.format(trace.event_count || 0)} events</span>
  `;
}

function benchmarkSessions(run) {
  if (run.sessions && run.sessions.length) return run.sessions;
  return (observation.sessions || []).filter((session) => {
    if (session.source_id !== run.source_id) return false;
    if (sessionRunId(session) !== run.run_id) return false;
    return (session.benchmarks || []).some((result) => result.benchmark === run.benchmark);
  });
}

function renderSessionTokenGrowthChart(session) {
  const points = tokenGrowthPoints(session);
  const chart = getChart("session-token-growth-chart");
  if (!points.length) {
    chart.setOption({
      title: { text: "No token samples captured", left: "center", top: "middle", textStyle: { color: "#8792a2", fontSize: 13, fontWeight: 500 } },
      xAxis: { type: "category", data: [] },
      yAxis: { type: "value" },
      series: []
    }, true);
    return;
  }
  chart.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      valueFormatter: (value) => fmt.format(value || 0)
    },
    legend: { top: 8, data: ["Input", "Output", "Cached Input", "Total"] },
    grid: { left: 76, right: 28, top: 52, bottom: 48 },
    xAxis: { type: "category", boundaryGap: false, data: points.map((point) => point.label) },
    yAxis: { type: "value", name: "tokens" },
    series: [
      { name: "Input", type: "line", smooth: true, showSymbol: points.length < 32, data: points.map((point) => point.input) },
      { name: "Output", type: "line", smooth: true, showSymbol: points.length < 32, data: points.map((point) => point.output) },
      { name: "Cached Input", type: "line", smooth: true, showSymbol: points.length < 32, data: points.map((point) => point.cachedInput) },
      { name: "Total", type: "line", smooth: true, showSymbol: points.length < 32, lineStyle: { width: 3 }, data: points.map((point) => point.total) }
    ]
  }, true);
}

function tokenGrowthPoints(session) {
  const events = (session.trace_events || [])
    .filter((event) => event.category === "tokens" && event.tokens)
    .sort((left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp));
  const points = events.map((event, index) => tokenPoint(event.tokens || {}, tokenPointLabel(event, index)));
  if (points.length) return points;
  const tokens = session.tokens || {};
  const fallback = tokenPoint(tokens, "final");
  return fallback.total > 0 ? [fallback] : [];
}

function tokenPoint(tokens, label) {
  const input = Number(tokens.input || 0);
  const output = Number(tokens.output || 0);
  const cachedInput = Number(tokens.cached_input || 0);
  return {
    label,
    input,
    output,
    cachedInput,
    total: Number(tokens.total || input + output)
  };
}

function tokenPointLabel(event, index) {
  const ms = timestampMs(event.timestamp);
  if (!Number.isFinite(ms)) return `#${index + 1}`;
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function timestampMs(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const numeric = Number(value);
  if (Number.isFinite(numeric) && String(value).trim() !== "") return numeric * 1000;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

async function refreshAllSources() {
  if (!sources.length) {
    setStatus("Static");
    return;
  }
  setStatus("Refreshing");
  for (const source of sources) {
    await triggerSource(source.id, "refresh", { quiet: true });
  }
  await loadDashboard();
}

async function triggerSource(sourceId, action, options = {}) {
  if (!sourceId || !action) return;
  if (!options.quiet) setStatus(action === "run" ? "Running" : "Refreshing");
  try {
    const payload = await fetchJson(`/api/sources/${encodeURIComponent(sourceId)}/${action}`, { method: "POST" });
    if (payload.error) throw new Error(payload.error.message);
    if (!options.quiet) await loadDashboard();
  } catch (error) {
    console.error(error);
    setStatus("API unavailable");
  }
}

async function loadSessionDetail(session) {
  if ((session.trace_events && session.trace_events.length) || (session.logs && session.logs.length)) return session;
  if (sessionDetails.has(session.session_id)) return sessionDetails.get(session.session_id);
  const apiUrl = `/api/sessions/${encodeURIComponent(session.session_id)}`;
  const payload = session.detail_json
    ? await fetchJson(session.detail_json).catch(() => fetchJson(apiUrl))
    : await fetchJson(apiUrl);
  const detail = payload.session || payload;
  sessionDetails.set(detail.session_id, detail);
  upsertSession(detail);
  return detail;
}

async function loadBenchmarkDetail(run) {
  const key = runKey(run);
  if (run.task_results || benchmarkDetails.has(key)) return benchmarkDetails.get(key) || run;
  const apiUrl = `/api/benchmarks/${encodeURIComponent(run.source_id)}/${encodeURIComponent(run.benchmark)}/${encodeURIComponent(run.run_id)}`;
  const payload = run.detail_json
    ? await fetchJson(run.detail_json).catch(() => fetchJson(apiUrl))
    : await fetchJson(apiUrl);
  const detail = payload.benchmark_run || payload;
  detail.task_results = payload.task_results || detail.task_results || [];
  detail.sessions = payload.sessions || detail.sessions || [];
  benchmarkDetails.set(key, detail);
  upsertBenchmarkRun(detail);
  return detail;
}

function upsertSession(session) {
  const sessions = observation.sessions || [];
  const index = sessions.findIndex((item) => item.session_id === session.session_id);
  if (index >= 0) sessions[index] = session;
  else sessions.push(session);
  observation.sessions = sessions;
}

function upsertBenchmarkRun(run) {
  const runs = observation.benchmark_runs || [];
  const key = runKey(run);
  const index = runs.findIndex((item) => runKey(item) === key);
  if (index >= 0) runs[index] = run;
  else runs.push(run);
  observation.benchmark_runs = runs;
}

function filteredSessions() {
  const sessions = observation.sessions || [];
  if (!selectedRun) return sessions;
  return sessions.filter((session) => {
    if (session.source_id !== selectedRun.source_id) return false;
    return session.benchmarks.some((benchmark) => {
      return benchmark.benchmark === selectedRun.benchmark && sessionRunId(session) === selectedRun.run_id;
    });
  });
}

function getChart(id) {
  if (!charts[id]) charts[id] = echarts.init(document.getElementById(id));
  return charts[id];
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

function setStatus(value) {
  document.getElementById("status").textContent = value;
}

function averageQuality(benchmarks) {
  if (!benchmarks.length) return 0;
  return benchmarks.reduce((sum, item) => sum + item.quality_score, 0) / benchmarks.length;
}

function observedBenchmarkNames() {
  const names = new Set();
  (observation.sessions || []).forEach((session) => {
    (session.benchmarks || []).forEach((result) => names.add(result.benchmark));
  });
  return Array.from(names).sort();
}

function sourceSessionSummary(sourceId) {
  const count = (observation.sessions || []).filter((session) => session.source_id === sourceId).length;
  return `${fmt.format(count)} sessions`;
}

function sourceBenchmarkSummary(sourceId) {
  const sourceSessions = (observation.sessions || []).filter((session) => session.source_id === sourceId);
  const benchmarkNames = new Set();
  const runs = new Set();
  let taskResults = 0;
  sourceSessions.forEach((session) => {
    (session.benchmarks || []).forEach((result) => {
      benchmarkNames.add(result.benchmark);
      runs.add(`${result.benchmark}::${sessionRunId(session)}`);
      taskResults += 1;
    });
  });
  if (!benchmarkNames.size) return "0 suites";
  return `${fmt.format(benchmarkNames.size)} suites · ${fmt.format(runs.size)} runs · ${fmt.format(taskResults)} task results`;
}

function sourceLabel(sourceId) {
  const source = sources.find((item) => item.id === sourceId);
  return source ? (source.label || source.id) : (sourceId || "manual");
}

function sessionRunId(session) {
  if (session.run_id) return session.run_id;
  if (session.start_time && session.start_time.length >= 10) return session.start_time.slice(0, 10);
  return "unassigned";
}

function pct(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function scoreText(value) {
  if (value === undefined || value === null) return "unknown";
  return Number(value).toFixed(2);
}

function secondsText(value) {
  return `${fmt.format(value || 0)}s`;
}

function sumValues(value) {
  return Object.values(value || {}).reduce((sum, item) => sum + item, 0);
}

function shortId(value) {
  return String(value || "").slice(0, 18);
}

function runKey(run) {
  return `${run.source_id}::${run.benchmark}::${run.run_id}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function numberFormatter(cell) {
  return fmt.format(cell.getValue() || 0);
}

function secondsFormatter(cell) {
  return `${fmt.format(cell.getValue() || 0)}s`;
}

function percentFormatter(cell) {
  return pct(cell.getValue() || 0);
}
