from __future__ import annotations

import json
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agentminmax.models import Observation
from agentminmax.traces import export_observation_traces


VENDOR_ASSET_DIR = Path(__file__).parent / "assets" / "vendor"
VENDOR_FILES = ("echarts.min.js", "tabulator.min.js", "tabulator.min.css")


def export_dashboard_bundle(observation: Observation, out_dir: str | Path) -> Path:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    export_observation_traces(observation, target)
    stale_trace_js = target / "trace.js"
    if stale_trace_js.exists():
        stale_trace_js.unlink()
    (target / "observations.json").write_text(json.dumps(observation.to_dict(), indent=2), encoding="utf-8")
    (target / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (target / "trace.html").write_text(TRACE_HTML, encoding="utf-8")
    (target / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (target / "app.js").write_text(APP_JS, encoding="utf-8")
    (target / "perfetto-embed.js").write_text(PERFETTO_EMBED_JS, encoding="utf-8")
    vendor_target = target / "vendor"
    vendor_target.mkdir(exist_ok=True)
    for filename in VENDOR_FILES:
        shutil.copyfile(VENDOR_ASSET_DIR / filename, vendor_target / filename)
    return target


def serve_dashboard(bundle_dir: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(bundle_dir).resolve()))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentMinMax dashboard serving at http://{host}:{port}/")
    server.serve_forever()


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentMinMax Observer</title>
  <link rel="stylesheet" href="vendor/tabulator.min.css">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="topbar">
    <div>
      <h1>AgentMinMax Observer</h1>
      <p>Dynamic trace panel for Codex sessions, session-derived benchmarks, and long-horizon agent work.</p>
    </div>
    <div class="top-actions">
      <button class="tool-button" id="refresh-all" type="button">Refresh</button>
      <div class="status-pill" id="status">Loading</div>
    </div>
  </header>

  <main class="layout">
    <section class="metric-grid" id="metric-grid" aria-label="Summary metrics"></section>

    <section class="panel wide source-panel">
      <div class="panel-head">
        <h2>Sources</h2>
        <span>session observation inputs and actions</span>
      </div>
      <div id="source-list" class="source-list"></div>
    </section>

    <section class="panel wide">
      <div class="panel-head">
        <h2>Sessions</h2>
        <span>select a row to open analysis panels</span>
      </div>
      <div id="session-table"></div>
      <div id="session-analysis" class="analysis-grid is-hidden" aria-live="polite" aria-hidden="true">
        <div class="analysis-head">
          <h2>Session Analysis</h2>
          <span id="session-analysis-context">select a session</span>
        </div>
        <article class="analysis-card wide">
          <h3>Overview</h3>
          <div id="session-overview-metrics" class="detail-metrics"></div>
        </article>
        <article class="analysis-card wide">
          <h3>Token Growth</h3>
          <div id="session-token-growth-chart" class="chart"></div>
        </article>
        <article class="analysis-card">
          <h3>Complexity</h3>
          <div id="session-complexity-chart" class="chart compact"></div>
        </article>
        <article class="analysis-card">
          <h3>Tokens And Tools</h3>
          <div id="session-token-tool-chart" class="chart compact"></div>
        </article>
        <article class="analysis-card">
          <h3>Code Changes</h3>
          <div id="session-code-metrics" class="detail-metrics"></div>
        </article>
        <article class="analysis-card">
          <h3>Related Benchmarks</h3>
          <div id="session-related-benchmarks" class="detail-chip-list"></div>
        </article>
        <article class="analysis-card wide">
          <h3>Trace Preview</h3>
          <div id="session-trace-links" class="trace-links"></div>
          <div class="perfetto-panel">
            <iframe id="session-perfetto-frame" class="perfetto-frame" src="https://ui.perfetto.dev/#!/?mode=embedded" title="Session Perfetto trace"></iframe>
            <div class="perfetto-status" id="session-perfetto-status">Select a session trace</div>
          </div>
        </article>
        <article class="analysis-card wide">
          <h3>Logs</h3>
          <div id="session-log-list" class="log-timeline"></div>
        </article>
      </div>
    </section>

    <section class="panel wide source-panel">
      <div class="panel-head">
        <h2>Benchmark Sources</h2>
        <span>run context from sources and observed suites</span>
      </div>
      <div id="benchmark-source-list" class="source-list"></div>
    </section>

    <section class="panel wide">
      <div class="panel-head">
        <h2>Benchmarks</h2>
        <span>select a row to open analysis panels</span>
      </div>
      <div id="benchmark-table"></div>
      <div id="benchmark-analysis" class="analysis-grid is-hidden" aria-live="polite" aria-hidden="true">
        <div class="analysis-head">
          <h2>Benchmark Analysis</h2>
          <span id="benchmark-analysis-context">select a benchmark</span>
        </div>
        <article class="analysis-card wide">
          <h3>Aggregate Metrics</h3>
          <div id="benchmark-aggregate-metrics" class="detail-metrics"></div>
        </article>
        <article class="analysis-card wide">
          <h3>Trace Preview</h3>
          <div id="benchmark-trace-links" class="trace-links"></div>
          <div class="perfetto-panel">
            <iframe id="benchmark-perfetto-frame" class="perfetto-frame" src="https://ui.perfetto.dev/#!/?mode=embedded" title="Benchmark Perfetto trace"></iframe>
            <div class="perfetto-status" id="benchmark-perfetto-status">Select a benchmark trace</div>
          </div>
        </article>
        <article class="analysis-card">
          <h3>Quality / Completion</h3>
          <div id="benchmark-quality-chart" class="chart compact"></div>
        </article>
        <article class="analysis-card">
          <h3>Cost Breakdown</h3>
          <div id="benchmark-cost-chart" class="chart compact"></div>
        </article>
        <article class="analysis-card">
          <h3>Contributing Sessions</h3>
          <div id="benchmark-session-list" class="detail-chip-list"></div>
        </article>
        <article class="analysis-card">
          <h3>Task Results</h3>
          <div id="benchmark-task-results" class="detail-task-list"></div>
        </article>
      </div>
    </section>
  </main>

  <script src="vendor/echarts.min.js"></script>
  <script src="vendor/tabulator.min.js"></script>
  <script src="perfetto-embed.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""


TRACE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentMinMax Perfetto Trace</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body class="trace-page" data-perfetto-page="true">
  <header class="topbar">
    <div>
      <h1>Perfetto Trace</h1>
      <p>Embedded Perfetto UI for Codex session and benchmark traces.</p>
    </div>
    <div class="top-actions">
      <a class="tool-button" id="download-trace" href="#">Download Perfetto JSON</a>
      <a class="tool-button" href="index.html">Dashboard</a>
      <div class="status-pill" id="status">Loading</div>
    </div>
  </header>
  <main class="perfetto-fullscreen">
    <iframe id="perfetto-frame" class="perfetto-frame full" src="https://ui.perfetto.dev/#!/?mode=embedded" title="Perfetto trace viewer"></iframe>
  </main>
  <script src="perfetto-embed.js"></script>
</body>
</html>
"""


STYLES_CSS = """:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --surface: #ffffff;
  --ink: #17202a;
  --muted: #667085;
  --line: #d8dee8;
  --green: #20805d;
  --blue: #2f6fed;
  --red: #b54708;
  --teal: #147d8a;
  --shadow: 0 8px 28px rgba(25, 31, 44, 0.08);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px clamp(18px, 4vw, 48px);
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

h1,
h2,
p {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: 28px;
  line-height: 1.1;
}

h2 {
  font-size: 16px;
  line-height: 1.2;
}

.topbar p,
.panel-head span,
.metric span,
td {
  color: var(--muted);
}

.topbar p {
  margin-top: 8px;
  font-size: 14px;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tool-button {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid #b9c4d5;
  border-radius: 8px;
  background: #fff;
  color: #253044;
  font-weight: 700;
  cursor: pointer;
}

.tool-button:hover {
  border-color: var(--blue);
  color: var(--blue);
}

.tool-button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.status-pill {
  min-width: 92px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  text-align: center;
  font-weight: 700;
  color: var(--teal);
  background: #eef9fa;
}

.layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  padding: 22px clamp(14px, 4vw, 48px) 42px;
}

.metric-grid {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.metric,
.panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.metric {
  padding: 16px;
  min-height: 104px;
}

.metric strong {
  display: block;
  margin-top: 10px;
  font-size: 25px;
  line-height: 1.1;
}

.metric span {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.panel {
  padding: 18px;
  min-height: 260px;
}

.source-panel {
  min-height: 130px;
}

.wide {
  grid-column: 1 / -1;
}

.chart {
  width: 100%;
  height: 280px;
  border: 1px solid #edf0f4;
  border-radius: 6px;
  background: #fbfcfe;
}

.chart.compact {
  height: 260px;
}

.trace-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.perfetto-panel {
  position: relative;
  min-height: 520px;
  margin-top: 12px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #ffffff;
}

.perfetto-frame {
  display: block;
  width: 100%;
  height: 520px;
  border: 0;
  background: #ffffff;
}

.perfetto-frame.full {
  height: calc(100vh - 104px);
  min-height: 620px;
}

.perfetto-status {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  max-width: min(420px, calc(100% - 24px));
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.92);
  font-size: 12px;
  box-shadow: 0 4px 18px rgba(25, 31, 44, 0.08);
}

.perfetto-fullscreen {
  padding: 0;
}

.source-list {
  display: grid;
  gap: 12px;
}

.source-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fbfcfe;
}

.source-main {
  min-width: 0;
}

.source-main strong,
.source-main span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-main span,
.source-meta {
  color: var(--muted);
  font-size: 12px;
}

.source-meta {
  text-align: right;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.panel-head span {
  font-size: 12px;
}

canvas {
  width: 100%;
  max-width: 100%;
  border: 1px solid #edf0f4;
  border-radius: 6px;
  background: #fbfcfe;
}

.tabulator {
  border: 1px solid #edf0f4;
  border-radius: 6px;
  background: #fbfcfe;
}

.tabulator .tabulator-header {
  border-bottom: 1px solid #d8dee8;
  background: #f6f7f9;
}

.tabulator-row.tabulator-selected {
  background: #eef9fa;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid #edf0f4;
}

.analysis-grid.is-hidden {
  display: none;
}

.analysis-head {
  grid-column: 1 / -1;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.analysis-head span {
  color: var(--muted);
  font-size: 12px;
}

.analysis-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fff;
}

.analysis-card.wide {
  grid-column: 1 / -1;
}

.analysis-card h3 {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.2;
}

.result-list,
.detail-list,
.detail-task-list,
.detail-chip-list {
  display: grid;
  gap: 10px;
}

.result-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px 12px;
  padding: 10px 0;
  border-bottom: 1px solid #edf0f4;
}

.result-item:last-child {
  border-bottom: 0;
}

.result-item strong {
  font-size: 14px;
}

.result-item span,
.empty {
  color: var(--muted);
  font-size: 12px;
}

.log-timeline {
  position: relative;
  display: grid;
  gap: 0;
  max-height: 560px;
  overflow-y: auto;
  padding: 4px 12px 4px 0;
  scrollbar-gutter: stable;
}

.log-entry {
  display: grid;
  grid-template-columns: 96px 22px minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
}

.log-time {
  padding-top: 10px;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.log-rail {
  position: relative;
  display: flex;
  justify-content: center;
}

.log-rail::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #dbe2ea;
}

.log-dot {
  position: relative;
  z-index: 1;
  width: 10px;
  height: 10px;
  margin-top: 13px;
  border: 2px solid #fff;
  border-radius: 999px;
  background: var(--blue);
  box-shadow: 0 0 0 1px #a9b8c8;
}

.log-entry.message .log-dot {
  background: var(--green);
}

.log-entry.tool .log-dot,
.log-entry.mcp .log-dot {
  background: #7c3aed;
}

.log-entry.tokens .log-dot {
  background: #d97706;
}

.log-entry.error .log-dot {
  background: var(--red);
}

.log-body {
  min-width: 0;
  padding: 8px 0 14px;
  border-bottom: 1px solid #edf0f4;
}

.log-entry:last-child .log-body {
  border-bottom: 0;
}

.log-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.log-title {
  min-width: 0;
}

.log-title strong,
.log-title span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-title strong {
  font-size: 13px;
}

.log-title span {
  color: var(--muted);
  font-size: 12px;
}

.log-token-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  min-width: 180px;
}

.log-token-chips span {
  padding: 3px 7px;
  border: 1px solid #e5eaf0;
  border-radius: 999px;
  color: #4b5563;
  background: #f8fafc;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.log-detail {
  margin-top: 7px;
  color: #374151;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.log-output {
  max-height: 180px;
  margin: 8px 0 0;
  overflow: auto;
  padding: 8px;
  border: 1px solid #edf0f4;
  border-radius: 6px;
  color: #1f2937;
  background: #f9fafb;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
}

.result-item.complete span:nth-child(3) {
  color: var(--green);
  font-weight: 700;
}

.result-item.incomplete span:nth-child(3) {
  color: var(--red);
  font-weight: 700;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.detail-section {
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fff;
}

.detail-section.wide {
  grid-column: 1 / -1;
}

.detail-section h3 {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.2;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-metric,
.detail-task,
.detail-chip {
  min-width: 0;
  padding: 8px;
  border: 1px solid #edf0f4;
  border-radius: 6px;
  background: #fbfcfe;
}

.detail-metric span,
.detail-task span,
.detail-chip span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.detail-metric strong,
.detail-task strong,
.detail-chip strong {
  display: block;
  margin-top: 4px;
  color: var(--ink);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.detail-task {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.detail-task.complete strong.status {
  color: var(--green);
}

.detail-task.incomplete strong.status {
  color: var(--red);
}

.detail-chip-list {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

th,
td {
  padding: 11px 10px;
  border-bottom: 1px solid #edf0f4;
  text-align: left;
  font-size: 13px;
  overflow-wrap: anywhere;
}

th {
  color: #344054;
  font-size: 12px;
  text-transform: uppercase;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .top-actions {
    width: 100%;
    justify-content: space-between;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .source-item {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .source-meta {
    text-align: left;
  }

  .detail-grid,
  .analysis-grid,
  .detail-metrics,
  .detail-chip-list,
  .detail-task {
    grid-template-columns: 1fr;
  }

  .log-entry {
    grid-template-columns: 72px 18px minmax(0, 1fr);
    gap: 8px;
  }

  .log-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .log-token-chips {
    justify-content: flex-start;
    min-width: 0;
  }

  h1 {
    font-size: 24px;
  }
}
"""


PERFETTO_EMBED_JS = """const AgentMinMaxPerfetto = (() => {
  const PERFETTO_URL = "https://ui.perfetto.dev/#!/?mode=embedded";
  const activeLoads = new Map();

  async function render({ frameId, statusId, trace, title }) {
    const frame = document.getElementById(frameId);
    const status = statusId ? document.getElementById(statusId) : null;
    if (!frame) return;
    const traceFile = trace && trace.perfetto_json;
    if (!traceFile) {
      setStatus(status, "No trace export available");
      return;
    }

    const token = `${frameId}:${traceFile}:${Date.now()}`;
    activeLoads.set(frameId, token);
    setStatus(status, "Loading trace");
    if (!frame.src || !frame.src.includes("mode=embedded")) frame.src = PERFETTO_URL;

    try {
      const response = await fetch(traceFile);
      if (!response.ok) throw new Error(`${response.status} ${traceFile}`);
      const buffer = await response.arrayBuffer();
      await waitForPerfetto(frame, token);
      if (activeLoads.get(frameId) !== token) return;
      frame.contentWindow.postMessage({
        perfetto: {
          buffer,
          title: title || traceFile,
          fileName: traceFile.split("/").pop(),
          localOnly: true,
          keepApiOpen: true
        }
      }, "*");
      setStatus(status, `Loaded in Perfetto · ${formatBytes(buffer.byteLength)}`);
    } catch (error) {
      console.error(error);
      setStatus(status, "Perfetto load failed");
    }
  }

  function waitForPerfetto(frame, token) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const interval = window.setInterval(() => {
        if (activeLoads.get(frame.id) !== token) {
          cleanup();
          resolve();
          return;
        }
        if (Date.now() - started > 15000) {
          cleanup();
          reject(new Error("Perfetto iframe did not respond"));
          return;
        }
        frame.contentWindow?.postMessage('PING', '*');
      }, 100);

      function onMessage(evt) {
        if (evt.source === frame.contentWindow && evt.data === 'PONG') {
          cleanup();
          resolve();
        }
      }

      function cleanup() {
        window.clearInterval(interval);
        window.removeEventListener("message", onMessage);
      }

      window.addEventListener("message", onMessage);
      frame.contentWindow?.postMessage('PING', '*');
    });
  }

  function initTracePage() {
    const params = new URLSearchParams(window.location.search);
    const file = params.get("file");
    const title = params.get("title") || file || "AgentMinMax trace";
    const download = document.getElementById("download-trace");
    if (download && file) download.href = file;
    render({
      frameId: "perfetto-frame",
      statusId: "status",
      trace: { perfetto_json: file },
      title
    });
  }

  function setStatus(node, value) {
    if (node) node.textContent = value;
  }

  function formatBytes(value) {
    if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${value} B`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body?.dataset.perfettoPage === "true") initTracePage();
  });

  return { render, initTracePage };
})();

window.AgentMinMaxPerfetto = AgentMinMaxPerfetto;
"""


APP_JS = """const fmt = new Intl.NumberFormat("en-US");

let observation = null;
let sources = [];
let selectedSession = null;
let selectedRun = null;
let sessionTable = null;
let benchmarkTable = null;
let charts = {};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh-all").addEventListener("click", refreshAllSources);
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
  renderMetrics(observation.summary);
  renderSourceList();
  renderBenchmarkSources();
  renderTables();
  renderSessionAnalysis(selectedSession);
  renderBenchmarkAnalysis(selectedRun ? selectedRun._run : null);
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

function selectSession(_event, row) {
  selectedSession = row.getData()._session;
  renderSessionAnalysis(selectedSession);
}

function selectBenchmarkRun(_event, row) {
  selectedRun = row.getData();
  renderBenchmarkAnalysis(selectedRun._run);
  renderSessionTable(filteredSessions());
}

function renderSessionAnalysis(session) {
  const panel = document.getElementById("session-analysis");
  setPanelVisibility(panel, Boolean(session));
  if (!session) return;

  const tokens = session.tokens || {};
  const code = session.code || {};
  const complexity = session.complexity || {};
  const model = session.model || {};
  const parameters = model.parameters || {};

  document.getElementById("session-analysis-context").textContent = `${session.session_id} · ${sourceLabel(session.source_id)}`;
  document.getElementById("session-overview-metrics").innerHTML = metricItems([
    ["Agent", session.agent || "unknown"],
    ["Model", model.name || "unknown"],
    ["Provider", model.provider || "unknown"],
    ["Size", parameters.declared_size || parameters.size || "unknown"],
    ["Status", session.status || "unknown"],
    ["Duration", secondsText(session.duration_seconds)],
    ["Total Tokens", fmt.format((tokens.input || 0) + (tokens.output || 0))],
    ["Tool Calls", fmt.format(sumValues(session.tool_calls))]
  ]);
  document.getElementById("session-code-metrics").innerHTML = metricItems([
    ["Files Changed", fmt.format(code.files_changed || 0)],
    ["Lines Added", fmt.format(code.lines_added || 0)],
    ["Lines Deleted", fmt.format(code.lines_deleted || 0)],
    ["Recommended Grain", complexity.recommended_grain || "unknown"]
  ]);
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
  renderSessionComplexityChart(session);
  renderSessionTokenToolChart(session);
}

function renderBenchmarkAnalysis(run) {
  const panel = document.getElementById("benchmark-analysis");
  setPanelVisibility(panel, Boolean(run));
  if (!run) return;

  const sessions = benchmarkSessions(run);

  document.getElementById("benchmark-analysis-context").textContent = `${run.benchmark} · ${run.run_id || "unassigned"}`;
  document.getElementById("benchmark-aggregate-metrics").innerHTML = metricItems([
    ["Source", sourceLabel(run.source_id)],
    ["Run", run.run_id || "unassigned"],
    ["Sessions", fmt.format(run.session_count || sessions.length)],
    ["Tasks", fmt.format(run.task_count || 0)],
    ["Completed", fmt.format(run.completed_count || 0)],
    ["Completion", pct(run.completion_rate)],
    ["Quality", pct(run.average_quality_score)],
    ["Tokens", fmt.format(run.total_tokens || 0)],
    ["Tool Calls", fmt.format(run.total_tool_calls || 0)],
    ["Duration", secondsText(run.total_duration_seconds)],
    ["Lines Changed", fmt.format(run.total_lines_changed || 0)]
  ]);
  document.getElementById("benchmark-session-list").innerHTML = sessionChipList(sessions);
  document.getElementById("benchmark-task-results").innerHTML = benchmarkTaskList(run);
  document.getElementById("benchmark-trace-links").innerHTML = renderTraceLinks(run.trace, `${run.benchmark} · ${run.run_id || "unassigned"}`);
  AgentMinMaxPerfetto.render({
    frameId: "benchmark-perfetto-frame",
    statusId: "benchmark-perfetto-status",
    trace: run.trace,
    title: `${run.benchmark} · ${run.run_id || "unassigned"}`
  });
  renderBenchmarkQualityChart(run);
  renderBenchmarkCostChart(run);
}

function setPanelVisibility(panel, visible) {
  panel.classList.toggle("is-hidden", !visible);
  panel.setAttribute("aria-hidden", visible ? "false" : "true");
}

function detailSection(title, content, wide = false) {
  return `<section class="detail-section${wide ? " wide" : ""}">
    <h3>${escapeHtml(title)}</h3>
    ${content}
  </section>`;
}

function metricItems(items) {
  return items.map(([label, value]) => `
    <div class="detail-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function metricGrid(items) {
  return `<div class="detail-metrics">${metricItems(items)}</div>`;
}

function objectMetricList(value) {
  const entries = Object.entries(value || {});
  if (!entries.length) return '<p class="empty">No tool calls captured.</p>';
  return metricGrid(entries.map(([label, count]) => [label, fmt.format(count || 0)]));
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
  return (observation.sessions || []).filter((session) => {
    if (session.source_id !== run.source_id) return false;
    if (sessionRunId(session) !== run.run_id) return false;
    return (session.benchmarks || []).some((result) => result.benchmark === run.benchmark);
  });
}

function renderSessionComplexityChart(session) {
  const complexity = session.complexity || {};
  const chart = getChart("session-complexity-chart");
  chart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 52, right: 22, top: 22, bottom: 42 },
    xAxis: { type: "category", data: ["Intrinsic", "Effective", "Chaos", "Absorption"] },
    yAxis: { type: "value", name: "score" },
    series: [
      {
        name: "Complexity",
        type: "bar",
        data: [
          complexity.intrinsic_score || 0,
          complexity.effective_score || 0,
          complexity.chaos_score || 0,
          complexity.model_absorption || 0
        ]
      }
    ]
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

function renderSessionTokenToolChart(session) {
  const tokens = session.tokens || {};
  const chart = getChart("session-token-tool-chart");
  chart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 62, right: 22, top: 22, bottom: 42 },
    xAxis: { type: "category", data: ["Input", "Output", "Cached", "Tool Calls"] },
    yAxis: { type: "value" },
    series: [
      {
        name: "Count",
        type: "bar",
        data: [
          tokens.input || 0,
          tokens.output || 0,
          tokens.cached_input || 0,
          sumValues(session.tool_calls)
        ]
      }
    ]
  });
}

function renderBenchmarkQualityChart(run) {
  const chart = getChart("benchmark-quality-chart");
  chart.setOption({
    tooltip: { trigger: "axis", formatter: (items) => items.map((item) => `${item.marker}${item.name}: ${pct(item.value)}`).join("<br>") },
    grid: { left: 52, right: 22, top: 22, bottom: 42 },
    xAxis: { type: "category", data: ["Completion", "Quality"] },
    yAxis: { type: "value", min: 0, max: 1, axisLabel: { formatter: (value) => pct(value) } },
    series: [
      {
        name: "Rate",
        type: "bar",
        data: [run.completion_rate || 0, run.average_quality_score || 0]
      }
    ]
  });
}

function renderBenchmarkCostChart(run) {
  const chart = getChart("benchmark-cost-chart");
  chart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 72, right: 22, top: 22, bottom: 42 },
    xAxis: { type: "category", data: ["Tokens", "Tools", "Duration", "Lines"] },
    yAxis: { type: "value" },
    series: [
      {
        name: "Cost",
        type: "bar",
        data: [
          run.total_tokens || 0,
          run.total_tool_calls || 0,
          run.total_duration_seconds || 0,
          run.total_lines_changed || 0
        ]
      }
    ]
  });
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
"""
