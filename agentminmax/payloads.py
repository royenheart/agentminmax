from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agentminmax.models import AgentSession, BenchmarkRun, Observation
from agentminmax.traces import benchmark_sessions, safe_trace_name


def observation_payload(observation: Observation) -> dict[str, Any]:
    return {
        "summary": asdict(observation.summary),
        "sessions": [session_summary_payload(session) for session in observation.sessions],
        "benchmark_runs": [benchmark_run_summary_payload(run) for run in observation.benchmark_runs],
        "sources": observation.sources,
    }


def session_detail_payload(session: AgentSession) -> dict[str, Any]:
    payload = asdict(session)
    payload["detail_json"] = session_detail_path(session)
    return {"session": payload}


def benchmark_run_detail_payload(run: BenchmarkRun, sessions: list[AgentSession]) -> dict[str, Any]:
    payload = benchmark_run_summary_payload(run)
    task_results = []
    for session in sessions:
        for result in session.benchmarks:
            if result.benchmark != run.benchmark:
                continue
            item = asdict(result)
            item["session_id"] = session.session_id
            task_results.append(item)
    payload["task_results"] = task_results
    payload["sessions"] = [session_summary_payload(session) for session in sessions]
    return {"benchmark_run": payload, "task_results": task_results, "sessions": payload["sessions"]}


def session_summary_payload(session: AgentSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "agent": session.agent,
        "model": asdict(session.model),
        "source_id": session.source_id,
        "run_id": session.run_id,
        "start_time": session.start_time,
        "end_time": session.end_time,
        "duration_seconds": session.duration_seconds,
        "status": session.status,
        "tokens": asdict(session.tokens),
        "tool_calls": dict(session.tool_calls),
        "benchmarks": [asdict(result) for result in session.benchmarks],
        "code": asdict(session.code),
        "complexity": asdict(session.complexity) if session.complexity else None,
        "metric_groups": [asdict(group) for group in session.metric_groups],
        "trace": _slim_trace(session.trace),
        "detail_json": session_detail_path(session),
    }


def benchmark_run_summary_payload(run: BenchmarkRun) -> dict[str, Any]:
    payload = asdict(run)
    payload["trace"] = _slim_trace(payload.get("trace") or {})
    payload["detail_json"] = benchmark_run_detail_path(run)
    return payload


def write_detail_payloads(observation: Observation, target: Any) -> None:
    session_dir = target / "details" / "sessions"
    benchmark_dir = target / "details" / "benchmarks"
    session_dir.mkdir(parents=True, exist_ok=True)
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    for session in observation.sessions:
        (target / session_detail_path(session)).write_text(
            _json_text(session_detail_payload(session)),
            encoding="utf-8",
        )

    for run in observation.benchmark_runs:
        sessions = benchmark_sessions(observation.sessions, run)
        (target / benchmark_run_detail_path(run)).write_text(
            _json_text(benchmark_run_detail_payload(run, sessions)),
            encoding="utf-8",
        )


def session_detail_path(session: AgentSession) -> str:
    return f"details/sessions/{safe_trace_name(session.session_id)}.json"


def benchmark_run_detail_path(run: BenchmarkRun) -> str:
    return (
        "details/benchmarks/"
        f"{safe_trace_name(run.source_id)}--{safe_trace_name(run.benchmark)}--{safe_trace_name(run.run_id)}.json"
    )


def benchmark_run_key(run: BenchmarkRun) -> tuple[str, str, str]:
    return (run.source_id, run.benchmark, run.run_id)


def _slim_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {key: trace[key] for key in ("event_count", "perfetto_json") if key in trace}


def _json_text(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
