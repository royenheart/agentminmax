from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from agentminmax.aggregation import aggregate_benchmark_runs
from agentminmax.benchmarks import benchmark_catalog, normalize_benchmark_result
from agentminmax.complexity import compute_complexity
from agentminmax.models import AgentSession, CodeMetrics, ModelInfo, Observation, ObservationSummary, TokenUsage


def load_jsonl_events(path: str | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL event") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{path}:{line_number}: event must be a JSON object")
        events.append(event)
    return events


def load_many_jsonl(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        events.extend(load_jsonl_events(path))
    return events


def normalize_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("type", ""))
        if event_type in {
            "session_start",
            "session_update",
            "session_end",
            "token_usage",
            "token_usage_total",
            "tool_call",
            "benchmark_result",
            "code_metric",
            "message",
            "log",
        }:
            normalized.append(event)
            continue

        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        timestamp = event.get("timestamp")
        event_source_id = event.get("source_id")

        if event_type == "session_meta":
            normalized.append(
                {
                    "type": "session_start",
                    "timestamp": payload.get("timestamp", timestamp),
                    "session_id": payload.get("id"),
                    "source_id": event_source_id,
                    "agent": payload.get("originator", payload.get("source", "codex")),
                    "provider": payload.get("model_provider", "unknown"),
                    "model": payload.get("model", "unknown"),
                    "model_parameters": _codex_session_parameters(payload),
                }
            )
        elif event_type == "turn_context":
            normalized.append(
                    {
                        "type": "session_update",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "model": payload.get("model"),
                    "model_parameters": {
                        "context_window": payload.get("model_context_window"),
                    },
                }
            )
        elif event_type == "event_msg":
            payload_type = str(payload.get("type", ""))
            if payload_type == "token_count":
                usage = (payload.get("info") or {}).get("total_token_usage") or {}
                normalized.append(
                    {
                        "type": "token_usage_total",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cached_input_tokens": usage.get("cached_input_tokens", 0),
                    }
                )
            elif payload_type in {"user_message", "agent_message"}:
                normalized.append(
                    {
                        "type": "message",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "role": payload_type.replace("_message", ""),
                        "content": payload.get("message", ""),
                    }
                )
        elif event_type == "response_item":
            payload_type = str(payload.get("type", ""))
            if payload_type == "function_call":
                normalized.append(
                    {
                        "type": "tool_call",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "tool": payload.get("name", "unknown_tool"),
                    }
                )
            elif payload_type == "message":
                normalized.append(
                    {
                        "type": "message",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "role": payload.get("role", "unknown"),
                        "content": _codex_message_content(payload),
                    }
                )
    return normalized


def build_observation(
    events: Iterable[dict[str, Any]],
    *,
    source_id: str = "manual",
    sources: list[dict[str, Any]] | None = None,
) -> Observation:
    sessions: list[AgentSession] = []
    current: AgentSession | None = None
    session_index = 0

    def ensure_session(event: dict[str, Any]) -> AgentSession:
        nonlocal current, session_index
        if current is not None:
            return current
        session_index += 1
        current = AgentSession(
            session_id=str(event.get("session_id", f"session-{session_index}")),
            agent=str(event.get("agent", "unknown")),
            model=ModelInfo(
                name=str(event.get("model", "unknown")),
                provider=str(event.get("provider", "unknown")),
                parameters=dict(event.get("model_parameters", {}) or {}),
            ),
            source_id=str(event.get("source_id", source_id)),
            run_id=str(event.get("run_id", _derive_run_id(_optional_timestamp(event)))),
        )
        sessions.append(current)
        return current

    for event in normalize_events(events):
        event_type = str(event.get("type", ""))
        if event_type == "session_start":
            session_index += 1
            current = AgentSession(
                session_id=str(event.get("session_id", f"session-{session_index}")),
                agent=str(event.get("agent", "unknown")),
                model=ModelInfo(
                    name=str(event.get("model", "unknown")),
                    provider=str(event.get("provider", "unknown")),
                    parameters=dict(event.get("model_parameters", {}) or {}),
                ),
                source_id=str(event.get("source_id", source_id)),
                run_id=str(event.get("run_id", _derive_run_id(_optional_timestamp(event)))),
                start_time=_optional_timestamp(event),
            )
            sessions.append(current)
            continue

        session = ensure_session(event)
        timestamp = _optional_timestamp(event)
        if timestamp:
            session.end_time = timestamp

        if event_type == "session_end":
            session.status = str(event.get("status", session.status))
            session.duration_seconds = _duration_seconds(session.start_time, session.end_time)
            current = None
        elif event_type == "session_update":
            if event.get("model"):
                session.model.name = str(event.get("model"))
            if event.get("provider"):
                session.model.provider = str(event.get("provider"))
            parameters = event.get("model_parameters") or {}
            if isinstance(parameters, dict):
                for key, value in parameters.items():
                    if value is not None:
                        session.model.parameters[key] = value
        elif event_type == "token_usage":
            session.tokens.input += _int_from_any(event, "input_tokens", "prompt_tokens")
            session.tokens.output += _int_from_any(event, "output_tokens", "completion_tokens")
            session.tokens.cached_input += _int_from_any(event, "cached_input_tokens")
        elif event_type == "token_usage_total":
            session.tokens.input = max(session.tokens.input, _int_from_any(event, "input_tokens", "prompt_tokens"))
            session.tokens.output = max(session.tokens.output, _int_from_any(event, "output_tokens", "completion_tokens"))
            session.tokens.cached_input = max(session.tokens.cached_input, _int_from_any(event, "cached_input_tokens"))
        elif event_type == "tool_call":
            tool = str(event.get("tool", event.get("name", "unknown_tool")))
            session.tool_calls[tool] = session.tool_calls.get(tool, 0) + 1
        elif event_type == "benchmark_result":
            session.benchmarks.append(normalize_benchmark_result(event))
        elif event_type == "code_metric":
            session.code.files_changed += _int_from_any(event, "files_changed")
            session.code.lines_added += _int_from_any(event, "lines_added")
            session.code.lines_deleted += _int_from_any(event, "lines_deleted")
        elif event_type in {"message", "log"}:
            text = str(event.get("content", event.get("message", ""))).strip()
            if text:
                session.logs.append(text[:500])

    for session in sessions:
        if session.duration_seconds == 0:
            session.duration_seconds = _duration_seconds(session.start_time, session.end_time)
        session.complexity = compute_complexity(session)

    return Observation(
        summary=summarize_sessions(sessions),
        sessions=sessions,
        benchmark_runs=aggregate_benchmark_runs(sessions),
        sources=sources or [],
        benchmark_catalog=benchmark_catalog(),
    )


def summarize_sessions(sessions: list[AgentSession]) -> ObservationSummary:
    all_benchmarks = [result for session in sessions for result in session.benchmarks]
    completed = sum(1 for result in all_benchmarks if result.completed)
    completion_rate = completed / len(all_benchmarks) if all_benchmarks else 0.0
    quality = (
        sum(result.quality_score for result in all_benchmarks) / len(all_benchmarks)
        if all_benchmarks
        else 0.0
    )
    return ObservationSummary(
        session_count=len(sessions),
        total_tokens=sum(session.tokens.total for session in sessions),
        total_tool_calls=sum(sum(session.tool_calls.values()) for session in sessions),
        total_lines_changed=sum(session.code.lines_changed for session in sessions),
        benchmark_completion_rate=round(completion_rate, 4),
        average_quality_score=round(quality, 4),
    )


def _optional_timestamp(event: dict[str, Any]) -> str | None:
    timestamp = event.get("timestamp")
    return str(timestamp) if timestamp else None


def _duration_seconds(start: str | None, end: str | None) -> int:
    if not start or not end:
        return 0
    try:
        start_dt = _parse_timestamp(start)
        end_dt = _parse_timestamp(end)
    except ValueError:
        return 0
    return max(int((end_dt - start_dt).total_seconds()), 0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _int_from_any(event: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = event.get(key)
        if value is None:
            continue
        return int(value)
    return 0


def _derive_run_id(timestamp: str | None) -> str:
    if not timestamp or len(timestamp) < 10:
        return "unassigned"
    return timestamp[:10]


def _codex_session_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = ("cwd", "cli_version", "source", "thread_source")
    return {key: payload[key] for key in allowed if payload.get(key) is not None}


def _codex_message_content(payload: dict[str, Any]) -> str:
    content = payload.get("content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)
