from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from agentminmax.models import AgentSession, BenchmarkRun


@dataclass
class _RunAccumulator:
    source_id: str
    benchmark: str
    run_id: str
    task_ids: set[str] = field(default_factory=set)
    session_ids: set[str] = field(default_factory=set)
    completed_count: int = 0
    quality_sum: float = 0.0
    result_count: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_duration_seconds: int = 0
    total_lines_changed: int = 0
    counted_sessions: set[str] = field(default_factory=set)


def aggregate_benchmark_runs(sessions: list[AgentSession]) -> list[BenchmarkRun]:
    groups: dict[tuple[str, str, str], _RunAccumulator] = {}
    for session in sessions:
        run_id = session.run_id or _derive_run_id(session.start_time)
        source_id = session.source_id or "manual"
        for result in session.benchmarks:
            key = (source_id, result.benchmark, run_id)
            accumulator = groups.setdefault(
                key,
                _RunAccumulator(source_id=source_id, benchmark=result.benchmark, run_id=run_id),
            )
            accumulator.task_ids.add(result.task_id)
            accumulator.session_ids.add(session.session_id)
            accumulator.completed_count += 1 if result.completed else 0
            accumulator.quality_sum += result.quality_score
            accumulator.result_count += 1
            if session.session_id not in accumulator.counted_sessions:
                accumulator.counted_sessions.add(session.session_id)
                accumulator.total_tokens += session.tokens.total
                accumulator.total_tool_calls += sum(session.tool_calls.values())
                accumulator.total_duration_seconds += session.duration_seconds
                accumulator.total_lines_changed += session.code.lines_changed

    return [
        BenchmarkRun(
            source_id=item.source_id,
            benchmark=item.benchmark,
            run_id=item.run_id,
            task_count=len(item.task_ids),
            session_count=len(item.session_ids),
            completed_count=item.completed_count,
            completion_rate=round(item.completed_count / item.result_count, 4) if item.result_count else 0.0,
            average_quality_score=round(item.quality_sum / item.result_count, 4) if item.result_count else 0.0,
            total_tokens=item.total_tokens,
            total_tool_calls=item.total_tool_calls,
            total_duration_seconds=item.total_duration_seconds,
            total_lines_changed=item.total_lines_changed,
        )
        for item in sorted(groups.values(), key=lambda run: (run.source_id, run.benchmark, run.run_id))
    ]


def _derive_run_id(start_time: str | None) -> str:
    if not start_time or len(start_time) < 10:
        return "unassigned"
    return start_time[:10]
