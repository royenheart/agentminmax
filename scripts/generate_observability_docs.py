#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from agentminmax.metrics import ATOMIC_EVENT_DEFINITIONS, BENCHMARK_METRICS, SESSION_METRICS, MetricDefinition


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOXYFILE = REPO_ROOT / "docs" / "observability" / "Doxyfile"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "observability" / "events-metrics.md"
DEFAULT_DOXYGEN_SUMMARY = (
    "Doxygen XML is generated from `agentminmax/metrics.py`, `agentminmax/models.py`, "
    "and `agentminmax/ingest.py`; this Markdown is rendered from those code comments "
    "plus live metric definition data."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate observability metrics Markdown from code documentation.")
    parser.add_argument("--doxyfile", type=Path, default=DEFAULT_DOXYFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run_doxygen(args.doxyfile)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_markdown().strip() + "\n", encoding="utf-8")


def run_doxygen(doxyfile: Path) -> None:
    executable = shutil.which("doxygen")
    if executable is None:
        raise SystemExit("doxygen is required. Install doxygen.")
    _doxygen_output_directory(doxyfile).mkdir(parents=True, exist_ok=True)
    subprocess.run([executable, str(doxyfile)], cwd=REPO_ROOT, check=True)


def _doxygen_output_directory(doxyfile: Path) -> Path:
    for line in doxyfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "OUTPUT_DIRECTORY":
            continue
        output = Path(value.strip())
        return output if output.is_absolute() else REPO_ROOT / output
    return REPO_ROOT


def build_markdown(*, doxygen_summary: str = DEFAULT_DOXYGEN_SUMMARY) -> str:
    lines = [
        "# AgentMinMax Events And Metrics",
        "",
        "Generated from Doxygen XML plus the live metric definitions in `agentminmax.metrics`.",
        doxygen_summary,
        "",
        "## Pipeline",
        "",
        "- `agentminmax.ingest.normalize_events()` converts native Codex logs and benchmark result records into normalized events.",
        "- `agentminmax.ingest.build_observation()` aggregates normalized events into `AgentSession` and `BenchmarkRun` models.",
        "- `agentminmax.metrics.enrich_session_metrics()` emits atomic events and grouped session metrics.",
        "- `agentminmax.metrics.enrich_benchmark_metrics()` emits grouped benchmark metrics from aggregated benchmark runs.",
        "- The dashboard renders the same event and metric objects; detail actions show each metric's inputs and formula.",
        "",
        "## Atomic Events",
        "",
        _event_table(),
        "",
        "## Session Metric Groups",
        "",
        *_metric_group_sections(SESSION_METRICS),
        "## Benchmark Metric Groups",
        "",
        *_metric_group_sections(BENCHMARK_METRICS),
        "## Regeneration",
        "",
        "Run `python scripts/generate_observability_docs.py` from the repository root with `doxygen` available on PATH. The command first invokes Doxygen with `docs/observability/Doxyfile`, then rewrites this Markdown file from the code-level event and metric definitions.",
        "",
    ]
    return "\n".join(lines)


def _event_table() -> str:
    rows = [
        "| Event | Category | Unit | Source | Meaning | Formula | Labels |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for event in ATOMIC_EVENT_DEFINITIONS:
        rows.append(
            "| "
            + " | ".join(
                [
                    _code(event.name),
                    event.category,
                    event.unit,
                    _escape_cell(event.source),
                    _escape_cell(event.description),
                    _code(event.formula or "direct observation"),
                    ", ".join(_code(label) for label in event.labels) or "none",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _metric_group_sections(definitions: Iterable[MetricDefinition]) -> list[str]:
    sections: list[str] = []
    for group_id, metrics in _group_metrics(definitions).items():
        group_label = metrics[0].group_label
        display = (metrics[0].display or {}).get("kind", "cards")
        sections.extend(
            [
                f"### {group_label}",
                "",
                f"- Group id: `{group_id}`",
                f"- Dashboard display: `{display}`",
                "",
                "| Metric | Unit | Meaning | Formula | Inputs |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for metric in metrics:
            sections.append(
                "| "
                + " | ".join(
                    [
                        _code(metric.metric_id),
                        metric.unit,
                        _escape_cell(metric.description),
                        _code(metric.formula or "direct observation"),
                        ", ".join(_code(item) for item in metric.inputs) or "none",
                    ]
                )
                + " |"
            )
        sections.append("")
    return sections


def _group_metrics(definitions: Iterable[MetricDefinition]) -> dict[str, list[MetricDefinition]]:
    groups: dict[str, list[MetricDefinition]] = defaultdict(list)
    for definition in definitions:
        groups[definition.group_id].append(definition)
    return dict(groups)


def _code(value: str) -> str:
    return f"`{_escape_cell(value)}`"


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
