from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from agentminmax.config import BenchmarkSource
from agentminmax.codex_logs import load_codex_log_events
from agentminmax.ingest import load_jsonl_events


def load_source_events(source: BenchmarkSource) -> list[dict[str, Any]]:
    if not source.enabled:
        return []
    if source.kind == "codex_logs":
        if not source.path:
            return []
        return load_codex_log_events(source.path, source_id=source.id)
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
        matches = glob.glob(str(Path(source.path).expanduser()), recursive=True)
        return sorted(Path(match) for match in matches if Path(match).is_file())
    if source.kind == "directory":
        if not source.path:
            return []
        root = Path(source.path).expanduser()
        if not root.exists():
            return []
        return sorted(path for path in root.rglob("*.jsonl") if path.is_file())
    if source.kind == "command":
        return []
    raise ValueError(f"unsupported source kind: {source.kind}")
