from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agentminmax.aggregation import aggregate_benchmark_runs
from agentminmax.benchmarks import benchmark_catalog, normalize_benchmark_result
from agentminmax.complexity import compute_complexity
from agentminmax.models import AgentSession, CodeMetrics, ModelInfo, Observation, ObservationSummary, TokenUsage, TraceEvent


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
            "trace_event",
            "trace_tool_output",
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
                    "run_id": event.get("run_id"),
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
                normalized.append(_codex_event_msg_trace(timestamp, payload))
            elif payload_type in {"user_message", "agent_message"}:
                role = payload_type.replace("_message", "")
                content = str(payload.get("message", ""))
                normalized.append(
                    {
                        "type": "message",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "role": role,
                        "content": content,
                    }
                )
                normalized.append(
                    _trace_event(
                        timestamp=timestamp,
                        category="message",
                        name=f"{role.title()} message",
                        lane="Messages",
                        summary=_short_text(content),
                        detail=content,
                        raw_type=payload_type,
                    )
                )
            elif payload_type in {"task_started", "task_complete", "patch_apply_end"}:
                normalized.append(_codex_event_msg_trace(timestamp, payload))
        elif event_type == "response_item":
            payload_type = str(payload.get("type", ""))
            if payload_type in {"function_call", "custom_tool_call"}:
                tool = str(payload.get("name") or ("apply_patch" if payload_type == "custom_tool_call" else "unknown_tool"))
                normalized.append(
                    {
                        "type": "tool_call",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "tool": tool,
                    }
                )
                normalized.append(_codex_tool_call_trace(timestamp, payload, tool))
            elif payload_type in {"function_call_output", "custom_tool_call_output"}:
                normalized.append(
                    {
                        "type": "trace_tool_output",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "call_id": payload.get("call_id"),
                        "output": payload.get("output", ""),
                        "status": _tool_output_status(str(payload.get("output", ""))),
                    }
                )
            elif payload_type == "reasoning":
                normalized.append(
                    _trace_event(
                        timestamp=timestamp,
                        category="reasoning",
                        name="Encrypted reasoning",
                        lane="Reasoning",
                        status="encrypted",
                        summary="Encrypted reasoning boundary",
                        detail="Reasoning content is encrypted by Codex and is not exposed.",
                        raw_type=payload_type,
                    )
                )
            elif payload_type == "message":
                content = _codex_message_content(payload)
                role = str(payload.get("role", "unknown"))
                normalized.append(
                    {
                        "type": "message",
                        "timestamp": timestamp,
                        "source_id": event_source_id,
                        "role": role,
                        "content": content,
                    }
                )
                normalized.append(
                    _trace_event(
                        timestamp=timestamp,
                        category="message",
                        name=f"{role.title()} message",
                        lane="Messages",
                        summary=_short_text(content),
                        detail=content,
                        raw_type=payload_type,
                    )
                )
    return normalized


def build_observation(
    events: Iterable[dict[str, Any]],
    *,
    source_id: str = "manual",
    sources: list[dict[str, Any]] | None = None,
) -> Observation:
    sessions: list[AgentSession] = []
    sessions_by_id: dict[str, AgentSession] = {}
    current: AgentSession | None = None
    session_index = 0
    trace_index = 0
    pending_trace_calls: dict[str, TraceEvent] = {}
    pending_turns: dict[str, TraceEvent] = {}

    def ensure_session(event: dict[str, Any]) -> AgentSession:
        nonlocal current, session_index
        event_session_id = event.get("session_id")
        if event_session_id:
            session_id = str(event_session_id)
            existing = sessions_by_id.get(session_id)
            if existing is not None:
                return existing
            session_index += 1
            session = AgentSession(
                session_id=session_id,
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
            sessions.append(session)
            sessions_by_id[session.session_id] = session
            return session
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
        sessions_by_id[current.session_id] = current
        return current

    for event in normalize_events(events):
        event_type = str(event.get("type", ""))
        if event_type == "session_start":
            session_index += 1
            session_id = str(event.get("session_id", f"session-{session_index}"))
            existing = sessions_by_id.get(session_id)
            if existing is not None:
                existing.agent = str(event.get("agent", existing.agent))
                if event.get("model"):
                    existing.model.name = str(event.get("model"))
                if event.get("provider"):
                    existing.model.provider = str(event.get("provider"))
                parameters = event.get("model_parameters") or {}
                if isinstance(parameters, dict):
                    for key, value in parameters.items():
                        if value is not None:
                            existing.model.parameters[key] = value
                if event.get("source_id"):
                    existing.source_id = str(event.get("source_id"))
                existing.run_id = str(event.get("run_id", existing.run_id))
                existing.start_time = _optional_timestamp(event) or existing.start_time
                current = existing
                continue
            current = AgentSession(
                session_id=session_id,
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
            sessions_by_id[current.session_id] = current
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
            if _int_from_any(event, "duration_ms") > 0:
                trace_index += 1
                session.trace_events.append(_generic_tool_call_trace(event, trace_index, tool))
        elif event_type == "trace_event":
            trace_index += 1
            trace_event = _build_trace_event(event, trace_index)
            turn_id = str(trace_event.args.get("turn_id") or "")
            turn_key = f"{session.session_id}:{turn_id}" if turn_id else ""
            if trace_event.raw_type == "task_started" and turn_id:
                pending_turns[turn_key] = trace_event
                session.trace_events.append(trace_event)
            elif trace_event.raw_type == "task_complete" and turn_key and turn_key in pending_turns:
                _complete_turn_trace_event(pending_turns.pop(turn_key), trace_event)
            else:
                session.trace_events.append(trace_event)
            if trace_event.call_id and trace_event.raw_type not in {"task_started", "task_complete"}:
                pending_trace_calls[trace_event.call_id] = trace_event
        elif event_type == "trace_tool_output":
            call_id = str(event.get("call_id") or "")
            pending = pending_trace_calls.get(call_id)
            if pending is None:
                continue
            pending.end_timestamp = timestamp
            pending.output = str(event.get("output", ""))
            pending.duration_ms = _duration_milliseconds(pending.timestamp, timestamp) or _wall_time_milliseconds(
                pending.output
            )
            pending.status = str(event.get("status", pending.status or "unknown"))
            if pending.output and not pending.detail:
                pending.detail = pending.output
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


def _duration_milliseconds(start: str | None, end: str | None) -> int:
    if not start or not end:
        return 0
    try:
        start_dt = _parse_timestamp(start)
        end_dt = _parse_timestamp(end)
    except ValueError:
        return 0
    return max(int((end_dt - start_dt).total_seconds() * 1000), 0)


def _wall_time_milliseconds(output: str) -> int:
    match = re.search(r"Wall time:\s*([0-9]+(?:\.[0-9]+)?)\s*seconds?", output)
    if not match:
        return 0
    return max(int(float(match.group(1)) * 1000), 1)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _coerce_timestamp(value: Any, fallback: str | None = None) -> str | None:
    if value is None or value == "":
        return fallback
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value)
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return datetime.fromtimestamp(float(text), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return text


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


def _trace_event(
    *,
    timestamp: str | None,
    category: str,
    name: str,
    lane: str,
    phase: str = "instant",
    status: str = "unknown",
    summary: str = "",
    detail: str = "",
    call_id: str | None = None,
    args: dict[str, Any] | None = None,
    output: str = "",
    tokens: dict[str, int] | None = None,
    raw_type: str = "",
) -> dict[str, Any]:
    return {
        "type": "trace_event",
        "timestamp": timestamp,
        "category": category,
        "name": name,
        "phase": phase,
        "lane": lane,
        "status": status,
        "summary": summary,
        "detail": detail,
        "call_id": call_id,
        "args": args or {},
        "output": output,
        "tokens": tokens or {},
        "raw_type": raw_type,
    }


def _codex_tool_call_trace(timestamp: str | None, payload: dict[str, Any], tool: str) -> dict[str, Any]:
    args = _parse_arguments(payload.get("arguments"))
    summary = tool
    if "cmd" in args:
        summary = str(args["cmd"])
    return _trace_event(
        timestamp=timestamp,
        category="tool",
        name=tool,
        phase="duration",
        lane=_tool_lane(tool),
        status="running",
        summary=_short_text(summary),
        detail=json.dumps(args, ensure_ascii=False, indent=2) if args else "",
        call_id=str(payload.get("call_id") or ""),
        args=args,
        raw_type=str(payload.get("type", "")),
    )


def _generic_tool_call_trace(event: dict[str, Any], index: int, tool: str) -> TraceEvent:
    duration_ms = _int_from_any(event, "duration_ms")
    status = str(event.get("status", "unknown"))
    args = dict(event.get("args", {}) or {})
    return TraceEvent(
        event_id=str(event.get("event_id") or f"tool-{index}"),
        category="tool",
        name=tool,
        phase="duration" if duration_ms > 0 else "instant",
        timestamp=_optional_timestamp(event),
        duration_ms=duration_ms,
        lane=_tool_lane(tool),
        status=status,
        summary=_short_text(str(event.get("summary") or tool)),
        detail=str(event.get("detail", "")),
        call_id=str(event.get("call_id")) if event.get("call_id") else None,
        args=args,
        output=str(event.get("output", "")),
        raw_type=str(event.get("raw_type", "tool_call")),
    )


def _tool_lane(tool: str) -> str:
    return "MCP Calls" if tool.startswith("mcp__") or tool.startswith("mcp.") else "Tool Calls"


def _codex_event_msg_trace(timestamp: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    payload_type = str(payload.get("type", ""))
    if payload_type == "token_count":
        usage = (payload.get("info") or {}).get("total_token_usage") or {}
        tokens = {
            "input": int(usage.get("input_tokens", 0) or 0),
            "output": int(usage.get("output_tokens", 0) or 0),
            "cached_input": int(usage.get("cached_input_tokens", 0) or 0),
        }
        return _trace_event(
            timestamp=timestamp,
            category="tokens",
            name="Token usage",
            phase="counter",
            lane="Token Usage",
            status="ok",
            summary=f"{tokens['input'] + tokens['output']} total tokens",
            tokens=tokens,
            raw_type=payload_type,
        )
    if payload_type == "patch_apply_end":
        success = bool(payload.get("success", True))
        path = str(payload.get("path", "patch"))
        return _trace_event(
            timestamp=timestamp,
            category="patch",
            name="Patch applied" if success else "Patch failed",
            lane="Patch / Files",
            status="ok" if success else "error",
            summary=path,
            detail=json.dumps(payload, ensure_ascii=False, indent=2),
            raw_type=payload_type,
        )
    if payload_type == "task_started":
        started_at = _coerce_timestamp(payload.get("started_at"), timestamp)
        args = {
            "turn_id": payload.get("turn_id"),
            "started_at": started_at,
        }
        return _trace_event(
            timestamp=started_at,
            category="lifecycle",
            name="Turn",
            lane="Lifecycle",
            status="running",
            summary="Turn started",
            detail=json.dumps(payload, ensure_ascii=False, indent=2),
            args={key: value for key, value in args.items() if value is not None},
            raw_type=payload_type,
        )
    completed_at = _coerce_timestamp(payload.get("completed_at"), timestamp)
    args = {
        "turn_id": payload.get("turn_id"),
        "completed_at": completed_at,
        "duration_ms": payload.get("duration_ms"),
        "time_to_first_token_ms": payload.get("time_to_first_token_ms"),
        "last_agent_message": payload.get("last_agent_message"),
    }
    return _trace_event(
        timestamp=completed_at,
        category="lifecycle",
        name="Task complete",
        lane="Lifecycle",
        status="ok",
        summary="Task complete",
        detail=json.dumps(payload, ensure_ascii=False, indent=2),
        args={key: value for key, value in args.items() if value is not None},
        raw_type=payload_type,
    )


def _build_trace_event(event: dict[str, Any], index: int) -> TraceEvent:
    return TraceEvent(
        event_id=str(event.get("event_id") or f"trace-{index}"),
        category=str(event.get("category", "event")),
        name=str(event.get("name", "event")),
        phase=str(event.get("phase", "instant")),
        timestamp=_optional_timestamp(event),
        end_timestamp=str(event.get("end_timestamp")) if event.get("end_timestamp") else None,
        duration_ms=_int_from_any(event, "duration_ms"),
        lane=str(event.get("lane", "agent")),
        status=str(event.get("status", "unknown")),
        summary=str(event.get("summary", "")),
        detail=str(event.get("detail", "")),
        call_id=str(event.get("call_id")) if event.get("call_id") else None,
        args=dict(event.get("args", {}) or {}),
        output=str(event.get("output", "")),
        tokens={key: int(value or 0) for key, value in dict(event.get("tokens", {}) or {}).items()},
        raw_type=str(event.get("raw_type", "")),
    )


def _complete_turn_trace_event(started: TraceEvent, completed: TraceEvent) -> None:
    started.name = "Turn"
    started.phase = "duration"
    started.status = completed.status
    started.end_timestamp = completed.timestamp
    started.args.update(completed.args)
    duration_ms = int(completed.args.get("duration_ms") or 0)
    started.duration_ms = duration_ms or _duration_milliseconds(started.timestamp, completed.timestamp)
    first_token_ms = int(completed.args.get("time_to_first_token_ms") or 0)
    summary_parts = []
    if started.duration_ms:
        summary_parts.append(f"{started.duration_ms / 1000:.1f}s turn")
    if first_token_ms:
        summary_parts.append(f"{first_token_ms / 1000:.1f}s first token")
    started.summary = " · ".join(summary_parts) or "Turn complete"
    last_agent_message = completed.args.get("last_agent_message")
    started.detail = str(last_agent_message) if last_agent_message is not None else completed.detail


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _tool_output_status(output: str) -> str:
    match = re.search(r"Process exited with code (-?\d+)", output)
    if match:
        return "ok" if match.group(1) == "0" else "error"
    if "Exit code: 0" in output:
        return "ok"
    return "unknown"


def _short_text(value: str, limit: int = 160) -> str:
    compact = " ".join(str(value).split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"
