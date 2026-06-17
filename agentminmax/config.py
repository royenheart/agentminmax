from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


SourceKind = Literal["jsonl_glob", "directory", "command", "codex_logs", "codex_home", "runs"]


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(slots=True)
class BenchmarkSource:
    id: str
    label: str
    kind: SourceKind
    path: str | None = None
    command: list[str] | None = None
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    last_status: str = "never"
    last_error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AgentMinMaxConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    sources: list[BenchmarkSource] = field(default_factory=list)


def load_config(path: str | Path) -> AgentMinMaxConfig:
    config_path = Path(path)
    if not config_path.exists():
        return default_config()
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    server_payload = payload.get("server", {})
    server = ServerConfig(
        host=str(server_payload.get("host", "127.0.0.1")),
        port=int(server_payload.get("port", 8765)),
    )
    sources = [source_from_dict(item) for item in payload.get("sources", [])]
    return AgentMinMaxConfig(server=server, sources=sources)


def default_config() -> AgentMinMaxConfig:
    return AgentMinMaxConfig(
        sources=[
            BenchmarkSource(
                id="local-codex",
                label="Local Codex Sessions",
                kind="codex_home",
                path="$CODEX_HOME",
                enabled=True,
                tags=["daily", "codex"],
            ),
            BenchmarkSource(
                id="benchmark-runs",
                label="Benchmark Run Directory",
                kind="runs",
                path="runs",
                enabled=True,
                tags=["benchmark"],
            ),
        ]
    )


def save_config(config: AgentMinMaxConfig, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[server]",
        f'host = "{_escape(config.server.host)}"',
        f"port = {config.server.port}",
        "",
    ]
    for source in config.sources:
        lines.extend(_source_to_toml(source))
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")


def source_from_dict(payload: dict) -> BenchmarkSource:
    source_id = str(payload.get("id", "")).strip()
    if not source_id:
        raise ValueError("source id must be non-empty")
    kind = str(payload.get("kind", "jsonl_glob"))
    if kind not in {"jsonl_glob", "directory", "command", "codex_logs", "codex_home", "runs"}:
        raise ValueError(f"unsupported source kind: {kind}")
    command = payload.get("command")
    return BenchmarkSource(
        id=source_id,
        label=str(payload.get("label", source_id)),
        kind=kind,  # type: ignore[arg-type]
        path=str(payload["path"]) if payload.get("path") is not None else None,
        command=[str(item) for item in command] if isinstance(command, list) else None,
        enabled=bool(payload.get("enabled", True)),
        tags=[str(item) for item in payload.get("tags", [])],
    )


def _source_to_toml(source: BenchmarkSource) -> list[str]:
    lines = [
        "[[sources]]",
        f'id = "{_escape(source.id)}"',
        f'label = "{_escape(source.label)}"',
        f'kind = "{source.kind}"',
        f"enabled = {_toml_bool(source.enabled)}",
        f"tags = [{', '.join(f'\"{_escape(tag)}\"' for tag in source.tags)}]",
    ]
    if source.path is not None:
        lines.append(f'path = "{_escape(source.path)}"')
    if source.command is not None:
        command = ", ".join(f'"{_escape(part)}"' for part in source.command)
        lines.append(f"command = [{command}]")
    return lines


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
