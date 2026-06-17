from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_run_events(path: str | Path, *, source_id: str = "benchmark-runs") -> list[dict[str, Any]]:
    root = _expand_path(path)
    if not root.exists():
        return []
    events: list[dict[str, Any]] = []
    for map_path in sorted(root.rglob("session_benchmark_map.json")):
        events.extend(_events_from_run_map(map_path, source_id=source_id))
    return events


def _events_from_run_map(map_path: Path, *, source_id: str) -> list[dict[str, Any]]:
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    run_dir = map_path.parent
    experiment_id = str(payload.get("experiment_id") or run_dir.name)
    results = _load_results(run_dir / "results.jsonl")
    events: list[dict[str, Any]] = []

    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        benchmark = str(entry.get("benchmark", "unknown"))
        task_id = str(entry.get("task_id", "unknown"))
        session_id = entry.get("session_id")
        if not session_id:
            continue
        run_id = str(entry.get("run_id") or experiment_id)
        result = results.get(("benchmark_result", benchmark, task_id), {})
        code_metric = results.get(("code_metric", benchmark, task_id), results.get(("code_metric", "", task_id), {}))

        result_event = {
            "type": "benchmark_result",
            "source_id": source_id,
            "session_id": session_id,
            "run_id": run_id,
            "benchmark": benchmark,
            "task_id": task_id,
            "completed": bool(result.get("completed", False)),
            "quality_score": result.get("quality_score"),
            "tests_passed": result.get("tests_passed", 0),
            "tests_total": result.get("tests_total", 0),
            "duration_seconds": result.get("duration_seconds", 0.0),
        }
        events.append(result_event)

        if code_metric:
            metric_event = {
                "type": "code_metric",
                "source_id": source_id,
                "session_id": session_id,
                "run_id": run_id,
                "files_changed": code_metric.get("files_changed", 0),
                "lines_added": code_metric.get("lines_added", 0),
                "lines_deleted": code_metric.get("lines_deleted", 0),
            }
            events.append(metric_event)

    return events


def _load_results(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL event") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{path}:{line_number}: event must be a JSON object")
        event_type = str(event.get("type", ""))
        benchmark = str(event.get("benchmark", ""))
        task_id = str(event.get("task_id", event.get("id", "")))
        if event_type in {"benchmark_result", "code_metric"} and task_id:
            results[(event_type, benchmark, task_id)] = event
    return results


def _expand_path(path: str | Path) -> Path:
    return Path(os.path.expandvars(str(path))).expanduser()
