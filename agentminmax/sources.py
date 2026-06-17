from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from agentminmax.config import BenchmarkSource
from agentminmax.codex_logs import load_codex_log_events
from agentminmax.ingest import load_jsonl_events
from agentminmax.runs import load_run_events


def load_source_events(source: BenchmarkSource) -> list[dict[str, Any]]:
    if not source.enabled:
        return []
    if source.kind == "codex_logs":
        if not source.path:
            return []
        return load_codex_log_events(_expand_path(source.path), source_id=source.id)
    if source.kind == "codex_home":
        if not source.path:
            return []
        return _load_codex_home_events(source.path, source_id=source.id)
    if source.kind == "runs":
        if not source.path:
            return []
        return load_run_events(source.path, source_id=source.id)
    paths = _source_paths(source)
    events: list[dict[str, Any]] = []
    for path in paths:
        for event in load_jsonl_events(path):
            event.setdefault("source_id", source.id)
            events.append(event)
    return events


def _source_paths(source: BenchmarkSource) -> list[Path]:
    if source.kind == "jsonl_glob":
        if not source.path:
            return []
        matches = glob.glob(str(_expand_path(source.path)), recursive=True)
        return sorted(Path(match) for match in matches if Path(match).is_file())
    if source.kind == "directory":
        if not source.path:
            return []
        root = _expand_path(source.path)
        if not root.exists():
            return []
        return sorted(path for path in root.rglob("*.jsonl") if path.is_file())
    if source.kind == "command":
        return []
    raise ValueError(f"unsupported source kind: {source.kind}")


def _load_codex_home_events(path: str | Path, *, source_id: str) -> list[dict[str, Any]]:
    root = _expand_path(path)
    sessions_root = root / "sessions" if (root / "sessions").exists() else root
    if not sessions_root.exists():
        return []
    events: list[dict[str, Any]] = []
    for session_path in sorted(sessions_root.rglob("*.jsonl")):
        for event in load_jsonl_events(session_path):
            event.setdefault("source_id", source_id)
            events.append(event)
    return events


def _expand_path(path: str | Path) -> Path:
    return Path(os.path.expandvars(str(path))).expanduser()
