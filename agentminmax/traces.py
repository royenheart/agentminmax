from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agentminmax.models import AgentSession, BenchmarkRun, Observation, TraceEvent


LANE_ORDER = {
    "Lifecycle": 1,
    "Messages": 2,
    "Reasoning": 3,
    "Tool Calls": 4,
    "Patch / Files": 5,
    "Token Usage": 6,
    "MCP Calls": 7,
}
DISPLAY_SLICE_US = 250_000
VISIBLE_SLICE_CATEGORIES = {"message", "reasoning", "tokens", "patch"}


def export_observation_traces(observation: Observation, out_dir: str | Path) -> None:
    target = Path(out_dir)
    session_dir = target / "traces" / "sessions"
    benchmark_dir = target / "traces" / "benchmarks"
    session_dir.mkdir(parents=True, exist_ok=True)
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    for session in observation.sessions:
        relative_path = f"traces/sessions/{safe_trace_name(session.session_id)}.json"
        session.trace = trace_summary(session.trace_events, relative_path)
        (target / relative_path).write_text(
            json.dumps(session_chrome_trace(session), indent=2),
            encoding="utf-8",
        )

    for run in observation.benchmark_runs:
        sessions = benchmark_sessions(observation.sessions, run)
        events = _benchmark_trace_events(sessions)
        relative_path = (
            "traces/benchmarks/"
            f"{safe_trace_name(run.source_id)}--{safe_trace_name(run.benchmark)}--{safe_trace_name(run.run_id)}.json"
        )
        run.trace = trace_summary(events, relative_path)
        (target / relative_path).write_text(
            json.dumps(benchmark_chrome_trace(run, sessions), indent=2),
            encoding="utf-8",
        )


def session_chrome_trace(session: AgentSession) -> dict[str, Any]:
    return {
        "displayTimeUnit": "ms",
        "metadata": {
            "name": session.session_id,
            "source_id": session.source_id,
            "run_id": session.run_id,
            "model": session.model.name,
        },
        "traceEvents": chrome_trace_events(session.trace_events, process_name=session.session_id),
    }


def benchmark_chrome_trace(run: BenchmarkRun, sessions: list[AgentSession]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for process_index, session in enumerate(sessions, start=1):
        events.extend(chrome_trace_events(session.trace_events, process_name=session.session_id, pid=process_index))
    return {
        "displayTimeUnit": "ms",
        "metadata": {
            "name": run.benchmark,
            "source_id": run.source_id,
            "run_id": run.run_id,
            "sessions": [session.session_id for session in sessions],
        },
        "traceEvents": events,
    }


def chrome_trace_events(trace_events: list[TraceEvent], *, process_name: str, pid: int = 1) -> list[dict[str, Any]]:
    base_us = _base_timestamp_us(trace_events)
    thread_names: dict[int, str] = {tid: lane for lane, tid in LANE_ORDER.items()}
    normalized_events = [
        (
            index,
            event,
            max(_timestamp_us(event.timestamp, fallback=index * 1000) - base_us, 0),
            _event_args(event),
        )
        for index, event in enumerate(trace_events)
    ]
    duration_tids = _duration_tids(normalized_events, thread_names)

    events: list[dict[str, Any]] = []
    for index, event, timestamp_us, args in normalized_events:
        tid = duration_tids.get(index, _base_tid(event.lane, thread_names))
        if _is_duration_event(event):
            events.append(
                {
                    "name": event.name,
                    "cat": event.category,
                    "ph": "X",
                    "ts": timestamp_us,
                    "dur": max(_duration_us(event), 1000),
                    "pid": pid,
                    "tid": tid,
                    "args": args,
                }
            )
            if event.category == "tokens":
                events.extend(_token_counter_events(event, timestamp_us, pid, thread_names))
        elif event.phase == "counter":
            events.append(
                {
                    "name": event.name,
                    "cat": event.category,
                    "ph": "C",
                    "ts": timestamp_us,
                    "pid": pid,
                    "tid": tid,
                    "args": event.tokens or args,
                }
            )
            if event.category == "tokens":
                events.extend(_token_counter_events(event, timestamp_us, pid, thread_names))
        else:
            events.append(
                {
                    "name": event.name,
                    "cat": event.category,
                    "ph": "I",
                    "s": "t",
                    "ts": timestamp_us,
                    "pid": pid,
                    "tid": tid,
                    "args": args,
                }
            )
    metadata = [{"name": "process_name", "ph": "M", "pid": pid, "tid": 0, "args": {"name": process_name}}]
    metadata.extend(
        {"name": "thread_name", "ph": "M", "pid": pid, "tid": tid, "args": {"name": name}}
        for tid, name in sorted(thread_names.items())
    )
    return metadata + events


def _duration_tids(
    normalized_events: list[tuple[int, TraceEvent, int, dict[str, Any]]],
    thread_names: dict[int, str],
) -> dict[int, int]:
    lane_levels: dict[str, list[int]] = {}
    event_tids: dict[int, int] = {}
    duration_events = [
        (index, event, timestamp_us)
        for index, event, timestamp_us, _args in normalized_events
        if _is_duration_event(event)
    ]
    for index, event, timestamp_us in sorted(duration_events, key=lambda item: (item[2], item[0])):
        duration_us = max(_duration_us(event), 1000)
        end_us = timestamp_us + duration_us
        levels = lane_levels.setdefault(event.lane, [])
        level = next((candidate for candidate, level_end in enumerate(levels) if timestamp_us >= level_end), len(levels))
        if level == len(levels):
            levels.append(end_us)
        else:
            levels[level] = end_us
        tid = _packed_tid(event.lane, level, thread_names)
        event_tids[index] = tid
    return event_tids


def _is_duration_event(event: TraceEvent) -> bool:
    return event.phase == "duration" or _actual_duration_us(event) > 0 or _is_visible_slice_event(event)


def _duration_us(event: TraceEvent) -> int:
    actual_duration = _actual_duration_us(event)
    if actual_duration > 0:
        return actual_duration
    if _is_visible_slice_event(event):
        return DISPLAY_SLICE_US
    return 0


def _actual_duration_us(event: TraceEvent) -> int:
    if event.duration_ms > 0:
        return event.duration_ms * 1000
    if event.timestamp and event.end_timestamp:
        return max(_timestamp_us(event.end_timestamp) - _timestamp_us(event.timestamp), 0)
    return 0


def _is_visible_slice_event(event: TraceEvent) -> bool:
    return event.category in VISIBLE_SLICE_CATEGORIES and event.phase in {"instant", "counter"}


def _token_counter_events(
    event: TraceEvent,
    timestamp_us: int,
    pid: int,
    thread_names: dict[int, str],
) -> list[dict[str, Any]]:
    if not event.tokens:
        return []
    input_tokens = int(event.tokens.get("input", 0) or 0)
    output_tokens = int(event.tokens.get("output", 0) or 0)
    cached_input_tokens = int(event.tokens.get("cached_input", 0) or 0)
    total_tokens = int(event.tokens.get("total", input_tokens + output_tokens) or 0)
    tracks = [
        ("Token Input", input_tokens),
        ("Token Output", output_tokens),
        ("Token Cached Input", cached_input_tokens),
        ("Token Total", total_tokens),
    ]
    return [
        {
            "name": name,
            "cat": "tokens",
            "ph": "C",
            "ts": timestamp_us,
            "pid": pid,
            "tid": _base_tid(name, thread_names),
            "args": {
                "value": value,
                "sample": event.event_id,
                "summary": event.summary,
            },
        }
        for name, value in tracks
    ]


def _packed_tid(lane: str, level: int, thread_names: dict[int, str]) -> int:
    base_tid = _base_tid(lane, thread_names)
    if level == 0:
        return base_tid
    tid = base_tid * 100 + level
    thread_names.setdefault(tid, f"{lane} {level + 1}")
    return tid


def _base_tid(lane: str, thread_names: dict[int, str]) -> int:
    if lane in LANE_ORDER:
        return LANE_ORDER[lane]
    for tid, name in thread_names.items():
        if name == lane:
            return tid
    tid = max(thread_names, default=999) + 1
    tid = max(tid, 1000)
    while tid in thread_names:
        tid += 1
    thread_names.setdefault(tid, lane)
    return tid


def trace_summary(events: list[TraceEvent], perfetto_json: str) -> dict[str, Any]:
    return {
        "event_count": len(events),
        "perfetto_json": perfetto_json,
        "preview_events": [preview_event(event) for event in events[:120]],
    }


def preview_event(event: TraceEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "category": event.category,
        "name": event.name,
        "phase": event.phase,
        "timestamp": event.timestamp,
        "duration_ms": event.duration_ms,
        "lane": event.lane,
        "status": event.status,
        "summary": event.summary,
        "detail": _truncate(event.detail or event.output, 1200),
        "args": event.args,
        "output": _truncate(event.output, 1200),
        "tokens": event.tokens,
    }


def benchmark_sessions(sessions: list[AgentSession], run: BenchmarkRun) -> list[AgentSession]:
    return [
        session
        for session in sessions
        if session.source_id == run.source_id
        and (session.run_id or _derive_run_id(session.start_time)) == run.run_id
        and any(result.benchmark == run.benchmark for result in session.benchmarks)
    ]


def safe_trace_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-")
    return safe or "trace"


def _benchmark_trace_events(sessions: list[AgentSession]) -> list[TraceEvent]:
    return [event for session in sessions for event in session.trace_events]


def _event_args(event: TraceEvent) -> dict[str, Any]:
    args: dict[str, Any] = {
        "event_id": event.event_id,
        "lane": event.lane,
        "status": event.status,
        "summary": event.summary,
    }
    if event.detail:
        args["detail"] = _truncate(event.detail, 4000)
    if event.call_id:
        args["call_id"] = event.call_id
    if event.args:
        args["args"] = event.args
    if event.output:
        args["output"] = _truncate(event.output, 4000)
    if event.tokens:
        args["tokens"] = event.tokens
    return args


def _base_timestamp_us(events: list[TraceEvent]) -> int:
    timestamps = [_timestamp_us(event.timestamp) for event in events if event.timestamp]
    return min(timestamps) if timestamps else 0


def _timestamp_us(value: str | None, fallback: int = 0) -> int:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return int(parsed.timestamp() * 1_000_000)


def _derive_run_id(start_time: str | None) -> str:
    if not start_time or len(start_time) < 10:
        return "unassigned"
    return start_time[:10]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"
