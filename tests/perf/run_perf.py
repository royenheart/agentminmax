from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agentminmax.dashboard import export_dashboard_bundle
from agentminmax.ingest import build_observation, load_jsonl_events


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "units" / "fixtures"


@dataclass(frozen=True, slots=True)
class PerfCase:
    case_id: str
    label: str
    run: Callable[[], Any]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run persistent AgentMinMax performance checks.")
    parser.add_argument("--history", default="perf-results/perf-history.jsonl")
    parser.add_argument("--output-dir", default="perf-results")
    parser.add_argument("--commit", default="local")
    parser.add_argument("--branch", default="local")
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args(argv)

    timestamp = args.timestamp or datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    records = run_perf_suite(
        history_path=Path(args.history),
        output_dir=Path(args.output_dir),
        commit=args.commit,
        branch=args.branch,
        timestamp=timestamp,
        rounds=max(args.rounds, 1),
    )
    print(json.dumps({"records": len(records), "output_dir": str(Path(args.output_dir))}, sort_keys=True))
    return 0


def run_perf_suite(
    *,
    history_path: Path,
    output_dir: Path,
    commit: str,
    branch: str,
    timestamp: str,
    rounds: int,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_history(history_path)
    records = [
        _measure_case(case, commit=commit, branch=branch, timestamp=timestamp, rounds=rounds)
        for case in _perf_cases()
    ]
    _write_history(history_path, [*existing, *records])
    history = _read_history(history_path)
    _write_summary(output_dir / "perf-summary.json", records, history, commit=commit, branch=branch, timestamp=timestamp)
    _write_json(output_dir / "perf-current.json", {"schema_version": 1, "records": records})
    _write_trend_svg(output_dir / "perf-trends.svg", history)
    _write_index(output_dir / "index.html", history, records)
    return records


def _perf_cases() -> list[PerfCase]:
    events = load_jsonl_events(FIXTURES / "codex-native-session.jsonl")

    return [
        PerfCase(
            case_id="ingest_codex_fixture",
            label="Ingest Codex Fixture",
            run=lambda: build_observation(events),
        ),
        PerfCase(
            case_id="dashboard_export_fixture",
            label="Export Dashboard Fixture",
            run=lambda: _export_dashboard(events),
        ),
    ]


def _export_dashboard(events: list[dict[str, Any]]) -> None:
    observation = build_observation(events)
    with tempfile.TemporaryDirectory(prefix="agentminmax-perf-") as temp_dir:
        export_dashboard_bundle(observation, temp_dir)


def _measure_case(case: PerfCase, *, commit: str, branch: str, timestamp: str, rounds: int) -> dict[str, Any]:
    durations: list[float] = []
    peaks: list[float] = []
    for _ in range(rounds):
        tracemalloc.start()
        started = time.perf_counter()
        case.run()
        duration_ms = (time.perf_counter() - started) * 1000
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        durations.append(duration_ms)
        peaks.append(peak_bytes / 1024)
    return {
        "schema_version": 1,
        "timestamp": timestamp,
        "commit": commit,
        "branch": branch,
        "case_id": case.case_id,
        "label": case.label,
        "duration_ms": round(statistics.median(durations), 3),
        "duration_min_ms": round(min(durations), 3),
        "duration_max_ms": round(max(durations), 3),
        "peak_kib": round(max(peaks), 3),
        "rounds": rounds,
    }


def _read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_history(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _write_summary(
    path: Path,
    records: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    commit: str,
    branch: str,
    timestamp: str,
) -> None:
    previous_by_case = _previous_records(history, commit=commit)
    cases = []
    for record in records:
        previous = previous_by_case.get(record["case_id"])
        delta_ms = None if previous is None else round(record["duration_ms"] - previous["duration_ms"], 3)
        delta_pct = None
        if previous and previous["duration_ms"]:
            delta_pct = round(delta_ms / previous["duration_ms"] * 100, 3)
        cases.append({**record, "previous_duration_ms": previous["duration_ms"] if previous else None, "delta_ms": delta_ms, "delta_pct": delta_pct})
    _write_json(
        path,
        {
            "schema_version": 1,
            "timestamp": timestamp,
            "commit": commit,
            "branch": branch,
            "history_records": len(history),
            "cases": cases,
        },
    )


def _previous_records(history: list[dict[str, Any]], *, commit: str) -> dict[str, dict[str, Any]]:
    previous: dict[str, dict[str, Any]] = {}
    for record in history:
        if record.get("commit") == commit:
            continue
        previous[record["case_id"]] = record
    return previous


def _write_trend_svg(path: Path, history: list[dict[str, Any]]) -> None:
    case_ids = sorted({record["case_id"] for record in history})
    if not history:
        path.write_text(_svg_page([], []), encoding="utf-8")
        return
    width = 920
    height = 360
    margin_left = 72
    margin_right = 24
    margin_top = 36
    margin_bottom = 72
    max_value = max(float(record["duration_ms"]) for record in history) or 1.0
    runs = _run_keys(history)
    x_positions = _positions(len(runs), margin_left, width - margin_right)
    colors = ["#2f6fed", "#2f6b4f", "#9a5bd6", "#c96a2b", "#147d8a"]
    polylines = []
    points = []
    for index, case_id in enumerate(case_ids):
        values_by_run = {(record["timestamp"], record["commit"]): record for record in history if record["case_id"] == case_id}
        coords = []
        for run_index, run_key in enumerate(runs):
            record = values_by_run.get(run_key)
            if not record:
                continue
            x = x_positions[run_index]
            y = _scale_y(float(record["duration_ms"]), max_value, margin_top, height - margin_bottom)
            coords.append(f"{x:.1f},{y:.1f}")
            points.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5"><title>{_escape(case_id)}: {record["duration_ms"]} ms @ {record["commit"]}</title></circle>'
            )
        if coords:
            color = colors[index % len(colors)]
            polylines.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(coords)}" />'
            )
    y_axis = "".join(_y_tick(value, max_value, margin_top, height - margin_bottom, width, margin_left) for value in _ticks(max_value))
    legend = "".join(
        f'<g transform="translate({margin_left + index * 210}, {height - 24})"><rect width="14" height="4" y="-8" fill="{colors[index % len(colors)]}" /><text x="20" y="-3">{_escape(case_id)}</text></g>'
        for index, case_id in enumerate(case_ids)
    )
    labels = "".join(
        f'<text class="x-label" x="{x_positions[index]:.1f}" y="{height - 48}" transform="rotate(35 {x_positions[index]:.1f} {height - 48})">{_escape(run_key[1][:8])}</text>'
        for index, run_key in enumerate(runs)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="AgentMinMax performance trends">
  <style>
    text {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #253044; font-size: 12px; }}
    .title {{ font-size: 18px; font-weight: 700; }}
    .axis {{ stroke: #94a3b8; stroke-width: 1; }}
    .grid {{ stroke: #e2e8f0; stroke-width: 1; }}
    .x-label {{ fill: #64748b; font-size: 11px; }}
  </style>
  <rect width="100%" height="100%" fill="#ffffff" />
  <text class="title" x="{margin_left}" y="24">AgentMinMax Performance Trends</text>
  <text x="{margin_left}" y="48">Median duration by commit, lower is better</text>
  {y_axis}
  <line class="axis" x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" />
  <line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" />
  {labels}
  {"".join(polylines)}
  {"".join(points)}
  {legend}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _svg_page(_case_ids: list[str], _history: list[dict[str, Any]]) -> str:
    return '<svg xmlns="http://www.w3.org/2000/svg" width="920" height="240"><text x="24" y="40">No perf history yet.</text></svg>\n'


def _run_keys(history: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted({(str(record["timestamp"]), str(record["commit"])) for record in history})


def _positions(count: int, left: float, right: float) -> list[float]:
    if count <= 1:
        return [(left + right) / 2]
    step = (right - left) / (count - 1)
    return [left + step * index for index in range(count)]


def _scale_y(value: float, max_value: float, top: float, bottom: float) -> float:
    return bottom - (value / max_value) * (bottom - top)


def _ticks(max_value: float) -> list[float]:
    return [max_value * value / 4 for value in range(5)]


def _y_tick(value: float, max_value: float, top: float, bottom: float, width: float, left: float) -> str:
    y = _scale_y(value, max_value, top, bottom)
    return f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - 24}" y2="{y:.1f}" /><text x="12" y="{y + 4:.1f}">{value:.1f} ms</text>'


def _write_index(path: Path, history: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    rows = "\n".join(
        f"<tr><td>{_escape(record['case_id'])}</td><td>{record['duration_ms']:.3f} ms</td><td>{record['peak_kib']:.1f} KiB</td><td>{_escape(record['commit'][:8])}</td></tr>"
        for record in records
    )
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentMinMax Perf Trends</title>
  <style>
    body {{ margin: 24px; color: #253044; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    table {{ border-collapse: collapse; margin-top: 20px; min-width: 640px; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 8px 12px; text-align: left; }}
    th {{ background: #f6f8fb; }}
  </style>
</head>
<body>
  <h1>AgentMinMax Perf Trends</h1>
  <p>{len(history)} persisted history records. Latest run has {len(records)} cases.</p>
  <img src="perf-trends.svg" alt="AgentMinMax performance trends">
  <table>
    <thead><tr><th>Case</th><th>Duration</th><th>Peak Memory</th><th>Commit</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


if __name__ == "__main__":
    raise SystemExit(main())
