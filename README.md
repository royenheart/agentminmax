# AgentMinMax

AgentMinMax is a research prototype for complexity-aware observability of long-horizon Codex and agent workflows.

It turns local Codex sessions, benchmark run outputs, token/tool traces, code-change signals, and model metadata into a dashboard for inspecting how an agent decomposes and executes work over time.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp agentminmax.toml.example agentminmax.toml
CODEX_HOME=${CODEX_HOME:-$HOME/.codex} .venv/bin/python -m agentminmax serve --config agentminmax.toml --bundle dashboard-dist --port 8765
```

Open `http://127.0.0.1:8765/` to view the local dashboard.

The default config reads Codex sessions from `$CODEX_HOME` and benchmark run outputs from `runs/`. Generated dashboard data, local experiment outputs, and copied session artifacts are ignored by git.

## Dashboard Preview

The dashboard includes sortable session and benchmark tables, hoverable charts, expandable analysis panels, logs with token context, and embedded Perfetto traces. The trace view makes long-running tool calls, messages, patch activity, lifecycle events, and token counters comparable on one timeline.

![Perfetto session trace preview](docs/assets/perfetto-session-trace.jpeg)

## Dashboard And Observability

The dynamic server exposes local `/api/*` endpoints and writes a static-compatible `dashboard-dist/` bundle. The initial observation payload is intentionally slim: it contains summary metrics and table rows only. Large session details, logs, and trace data are loaded lazily when a row is selected.

Captured session metrics include:

- model name, provider, context window, and declared model size when available
- total input, output, and cached input tokens
- tool-call counts split by tool name, including MCP calls
- duration, status, session source, and run identifier
- code changes from normalized `code_metric` events and native Codex `patch_apply_end.changes`
- benchmark associations by source, suite, run, task, and quality score
- complexity estimates: intrinsic score, effective score, model absorption, chaos score, and recommended grain

Trace visualization includes:

- message, reasoning, lifecycle, tool-call, MCP, patch/file, and token lanes
- duration blocks for tool calls and known timed events
- token counter tracks for input, output, cached input, and total tokens
- exported Perfetto JSON for full-screen inspection or download

For large sessions, the dashboard exports pre-compressed JSON assets and serves gzip when the browser supports it. This keeps the first screen small while still allowing full trace inspection.

## Data Sources

`agentminmax.toml` defines where sessions and benchmark outputs live. Agent sessions and benchmark outcomes are separate streams.

Supported source kinds:

- `codex_home`: reads native Codex JSONL sessions below `$CODEX_HOME/sessions`
- `runs`: reads `runs/**/session_benchmark_map.json` and adjacent `results.jsonl`
- `jsonl_glob`: reads matching normalized JSONL traces
- `directory`: recursively reads `.jsonl` files below a directory
- `command`: executes the configured command, records a job result, and then refreshes observations

Native Codex session ingestion recognizes:

- `session_meta` and `turn_context` for session/model metadata
- `event_msg` token counts, messages, lifecycle events, and patch results
- `response_item` function calls, tool outputs, reasoning boundaries, and assistant/user messages
- `patch_apply_end.changes` for files changed, lines added, and lines deleted

Normalized AgentMinMax JSONL remains supported for synthetic or external agents:

```json
{"type":"session_start","session_id":"s1","timestamp":"2026-06-16T01:00:00Z","agent":"codex","model":"gpt-5-codex","model_parameters":{"declared_size":"1T"}}
{"type":"token_usage","input_tokens":1200,"output_tokens":800}
{"type":"tool_call","tool":"exec_command","duration_ms":300}
{"type":"benchmark_result","benchmark":"swe-bench-verified","task_id":"demo","completed":true,"quality_score":0.82}
{"type":"code_metric","files_changed":4,"lines_added":120,"lines_deleted":20}
{"type":"session_end","timestamp":"2026-06-16T01:05:30Z","status":"completed"}
```

## Experiments And Benchmarks

Run the built-in six-task live experiment:

```bash
CODEX_HOME=$HOME/.codex .venv/bin/python experiments.py
```

The experiment writes task workspaces, `results.jsonl`, and `session_benchmark_map.json` under `runs/<experiment-id>/`. The dashboard uses that map to connect benchmark tasks back to the Codex sessions that produced them.

Run a preconfigured benchmark command source:

```bash
.venv/bin/python -m agentminmax run-benchmark custom-runner --config agentminmax.toml --bundle dashboard-dist
```

Third-party benchmark collections are managed by scripts rather than vendored into git:

```bash
.venv/bin/python tests/e2e/benchmarks/fetch_benchmarks.py
```

Fetched collections are placed under `tests/e2e/benchmarks/third_party`, which is ignored by git.

## CLI Utilities

Summarize a normalized JSONL fixture:

```bash
.venv/bin/python -m agentminmax summarize tests/units/fixtures/codex-session.jsonl
```

Export a static dashboard bundle:

```bash
.venv/bin/python -m agentminmax collect tests/units/fixtures/codex-session.jsonl --out dashboard-dist
```

Scan common Codex locations:

```bash
.venv/bin/python -m agentminmax scan-codex
.venv/bin/python -m agentminmax scan-codex --out dashboard-dist
```

## Frontend Assets

Dashboard HTML, CSS, and JavaScript live under `agentminmax/assets/dashboard/`. The Python exporter copies these resources into `dashboard-dist/` and adds vendored ECharts, Tabulator, and Perfetto embed support.

The frontend uses:

- Apache ECharts for token, complexity, quality, and cost charts
- Tabulator for sortable/filterable session and benchmark tables
- Perfetto embedded UI for full trace browsing
- CSS-only loading overlays for analysis panels while session or benchmark details are being parsed

## Tests

Unit tests live under `tests/units`. The files in `tests/units/fixtures` are small deterministic parser fixtures only.

End-to-end benchmark management lives under `tests/e2e/benchmarks`.

```bash
.venv/bin/python -m pytest -q
```

## Current Scope

AgentMinMax is still a research prototype. It is useful for exploring goal granularity, local versus global optimization, benchmark aggregation from session observations, and how model scale changes the grain of agent work. It is not yet a full telemetry platform, but the current architecture has explicit extension points for additional agent runtimes, richer benchmark adapters, and alternate trace viewers.
