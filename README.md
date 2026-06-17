# AgentMinMax

AgentMinMax is a research prototype for complexity-aware observability of long-horizon Codex and agent workflows.

It provides:

- A normalized observation schema for agent sessions, model metadata, tokens, tool calls, code size, benchmark results, and relative complexity.
- A Python CLI for summarizing JSONL traces, producing demo data, exporting dashboard bundles, and serving the web panel.
- A repo-local Codex plugin scaffold in `plugins/agentminmax-observer`.
- A static dashboard that can be opened by any HTTP server and reused across benchmark runs or daily Codex work.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
CODEX_HOME=${CODEX_HOME:-$HOME/.codex} .venv/bin/python experiments.py --dry-run
cp agentminmax.toml.example agentminmax.toml
.venv/bin/python -m agentminmax serve --config agentminmax.toml --bundle dashboard-dist --port 8765
```

Open `http://127.0.0.1:8765/` to view the panel.

For the dynamic local panel:

```bash
cp agentminmax.toml.example agentminmax.toml
.venv/bin/python -m agentminmax serve --config agentminmax.toml --bundle dashboard-dist --port 8765
```

The dynamic server adds local `/api/*` endpoints. By default, it reads Codex sessions from `$CODEX_HOME` and experiment benchmark mappings from `runs/`.

## Trace Input

AgentMinMax accepts two JSONL forms:

- Native Codex session logs under common locations such as `~/.codex/sessions`.
- Normalized AgentMinMax events where each line is one event:

```json
{"type":"session_start","session_id":"s1","timestamp":"2026-06-16T01:00:00Z","agent":"codex","model":"gpt-5-codex","model_parameters":{"declared_size":"1T"}}
{"type":"token_usage","input_tokens":1200,"output_tokens":800}
{"type":"tool_call","tool":"exec_command","duration_ms":300}
{"type":"benchmark_result","benchmark":"swe-bench-verified","task_id":"demo","completed":true,"quality_score":0.82}
{"type":"code_metric","files_changed":4,"lines_added":120,"lines_deleted":20}
{"type":"session_end","timestamp":"2026-06-16T01:05:30Z","status":"completed"}
```

Summarize the unit fixture:

```bash
.venv/bin/python -m agentminmax summarize tests/units/fixtures/codex-session.jsonl
```

Export a dashboard bundle:

```bash
.venv/bin/python -m agentminmax collect tests/units/fixtures/codex-session.jsonl --out dashboard-dist
```

Scan common Codex locations:

```bash
.venv/bin/python -m agentminmax scan-codex
.venv/bin/python -m agentminmax scan-codex --out dashboard-dist
```

Run a preconfigured benchmark source:

```bash
.venv/bin/python -m agentminmax run-benchmark custom-runner --config agentminmax.toml --bundle dashboard-dist
```

Run the built-in six-task live experiment:

```bash
CODEX_HOME=$HOME/.codex .venv/bin/python experiments.py
```

The experiment writes task workspaces, `results.jsonl`, and `session_benchmark_map.json` under `runs/<experiment-id>/`.

## Dynamic Sources

`agentminmax.toml` defines where sessions and benchmark outputs live. Agent sessions and benchmark outcomes are separate streams: Codex sessions come from `$CODEX_HOME`, while benchmark outcomes and the session-to-task map come from `runs/`.

Supported source kinds:

- `codex_home`: reads native Codex JSONL sessions below `$CODEX_HOME/sessions`.
- `runs`: reads `runs/**/session_benchmark_map.json` and adjacent `results.jsonl`.
- `jsonl_glob`: reads matching JSONL traces.
- `directory`: recursively reads `.jsonl` files below a directory.
- `command`: executes the configured command and records a job result, then refreshes observations from configured sources.

## Tests and Benchmarks

Unit tests live under `tests/units`. The files in `tests/units/fixtures` are small deterministic parser fixtures only.

End-to-end benchmark management lives under `tests/e2e/benchmarks`. Third-party benchmark collections are fetched into `tests/e2e/benchmarks/third_party`, which is ignored by git:

```bash
.venv/bin/python tests/e2e/benchmarks/fetch_benchmarks.py
```

The dashboard uses Apache ECharts for hoverable charts and Tabulator for sortable/filterable session and benchmark tables. Static exports still work because the frontend assets are vendored into the bundle.

## Current Scope

This is the first research scaffold, not a finished telemetry product. It already provides the end-to-end path from trace events to quantitative dashboard, while leaving clear extension points for real Codex session discovery, OpenTelemetry ingestion, and benchmark-specific adapters.
