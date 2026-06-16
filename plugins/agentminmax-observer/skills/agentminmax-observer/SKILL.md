---
name: agentminmax-observer
description: Use when the user wants to collect, summarize, compare, or visualize Codex/agent session metrics, benchmark results, tool calls, token usage, code scale, or complexity.
---

# AgentMinMax Observer

Use this skill to turn agent work into quantitative observations.

## Workflow

1. Locate JSONL traces or benchmark result files.
2. Run the local AgentMinMax CLI from the repository root.
3. Export a dashboard bundle with normalized observations.
4. Serve the dashboard and verify that it renders.

## Commands

Create a demo bundle:

```bash
.venv/bin/python -m agentminmax demo --out dashboard-dist
```

Summarize a trace:

```bash
.venv/bin/python -m agentminmax summarize path/to/session.jsonl
```

Collect one or more traces:

```bash
.venv/bin/python -m agentminmax collect 'runs/**/*.jsonl' --out dashboard-dist
```

Serve a bundle:

```bash
.venv/bin/python -m agentminmax dashboard --bundle dashboard-dist --port 8765
```

Serve a dynamic local dashboard:

```bash
.venv/bin/python -m agentminmax serve --config agentminmax.toml --bundle dashboard-dist --port 8765
```

Run a configured benchmark source:

```bash
.venv/bin/python -m agentminmax run-benchmark custom-runner --config agentminmax.toml --bundle dashboard-dist
```

Scan common Codex locations:

```bash
.venv/bin/python -m agentminmax scan-codex --out dashboard-dist
```

Native Codex session JSONL is supported through `session_meta`, `turn_context`, `event_msg`, and `response_item` adaptation. Normalized AgentMinMax JSONL remains useful for synthetic benchmark runs and non-Codex agents.

## Current Metrics

- Session count and duration
- Native Codex session metadata
- Model name and declared model size
- Input, output, and cached input tokens
- Tool call counts
- Benchmark completion and quality scores aggregated from sessions
- Files and lines changed
- Relative complexity and recommended goal grain
- Configured source status and command job results

## Dynamic Panel

The dynamic panel uses vendored Apache ECharts and Tabulator assets. Charts show exact values on hover. Tables support sorting, filtering, and row selection. Browser-triggered runs are limited to commands already declared in `agentminmax.toml`.

## Notes

This plugin does not claim that every Codex runtime log schema is already stable. When real session logs use a different shape, add a small adapter while preserving the normalized AgentMinMax observation schema.
