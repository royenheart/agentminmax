from __future__ import annotations

import glob
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agentminmax.config import BenchmarkSource
from agentminmax.codex_logs import load_codex_log_events
from agentminmax.ingest import load_jsonl_events
from agentminmax.runs import load_run_events


class ObservationSource(ABC):
    def __init__(self, source: BenchmarkSource) -> None:
        self.source = source

    def load_events(self) -> list[dict[str, Any]]:
        if not self.source.enabled:
            return []
        return self._load_enabled_events()

    @abstractmethod
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _with_source_id(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for event in events:
            event.setdefault("source_id", self.source.id)
        return events


class JsonlGlobSource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for path in self._paths():
            events.extend(load_jsonl_events(path))
        return self._with_source_id(events)

    def _paths(self) -> list[Path]:
        if not self.source.path:
            return []
        matches = glob.glob(str(_expand_path(self.source.path)), recursive=True)
        return sorted(Path(match) for match in matches if Path(match).is_file())


class DirectorySource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for path in self._paths():
            events.extend(load_jsonl_events(path))
        return self._with_source_id(events)

    def _paths(self) -> list[Path]:
        if not self.source.path:
            return []
        root = _expand_path(self.source.path)
        if not root.exists():
            return []
        return sorted(path for path in root.rglob("*.jsonl") if path.is_file())


class CodexLogsSource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        if not self.source.path:
            return []
        return load_codex_log_events(_expand_path(self.source.path), source_id=self.source.id)


class CodexHomeSource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        if not self.source.path:
            return []
        return _load_codex_home_events(self.source.path, source_id=self.source.id)


class RunsSource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        if not self.source.path:
            return []
        return load_run_events(self.source.path, source_id=self.source.id)


class CommandSource(ObservationSource):
    def _load_enabled_events(self) -> list[dict[str, Any]]:
        return []


def source_loader_for(source: BenchmarkSource) -> ObservationSource:
    if source.kind == "jsonl_glob":
        return JsonlGlobSource(source)
    if source.kind == "directory":
        return DirectorySource(source)
    if source.kind == "codex_logs":
        return CodexLogsSource(source)
    if source.kind == "codex_home":
        return CodexHomeSource(source)
    if source.kind == "runs":
        return RunsSource(source)
    if source.kind == "command":
        return CommandSource(source)
    raise ValueError(f"unsupported source kind: {source.kind}")


def load_source_events(source: BenchmarkSource) -> list[dict[str, Any]]:
    return source_loader_for(source).load_events()


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
