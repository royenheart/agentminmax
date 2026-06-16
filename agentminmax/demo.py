from __future__ import annotations

from agentminmax.ingest import build_observation
from agentminmax.models import Observation


def demo_observation() -> Observation:
    events = [
        {
            "type": "session_start",
            "session_id": "codex-20b-frontend",
            "timestamp": "2026-06-16T02:00:00Z",
            "agent": "codex",
            "model": "frontier-small",
            "model_parameters": {"declared_size": "20B", "context_window": 128000},
        },
        {"type": "message", "content": "Human feedback: the first visual implementation is too plain."},
        {"type": "token_usage", "input_tokens": 3800, "output_tokens": 2200},
        {"type": "tool_call", "tool": "exec_command"},
        {"type": "tool_call", "tool": "exec_command"},
        {"type": "tool_call", "tool": "apply_patch"},
        {
            "type": "benchmark_result",
            "benchmark": "visualwebarena",
            "task_id": "dashboard-layout",
            "completed": False,
            "quality_score": 0.52,
            "tests_passed": 5,
            "tests_total": 10,
        },
        {"type": "code_metric", "files_changed": 9, "lines_added": 620, "lines_deleted": 180},
        {"type": "session_end", "timestamp": "2026-06-16T02:21:00Z", "status": "needs_review"},
        {
            "type": "session_start",
            "session_id": "codex-1t-benchmark",
            "timestamp": "2026-06-16T03:00:00Z",
            "agent": "codex",
            "model": "gpt-5-codex",
            "model_parameters": {"declared_size": "1T", "context_window": 1000000},
        },
        {"type": "message", "content": "Codex task: normalize benchmark traces and expose session metrics."},
        {"type": "token_usage", "input_tokens": 2400, "output_tokens": 1700, "cached_input_tokens": 600},
        {"type": "tool_call", "tool": "exec_command"},
        {"type": "tool_call", "tool": "apply_patch"},
        {
            "type": "benchmark_result",
            "benchmark": "swe-bench-verified",
            "task_id": "repo-observability",
            "completed": True,
            "quality_score": 0.84,
            "tests_passed": 21,
            "tests_total": 24,
        },
        {"type": "code_metric", "files_changed": 6, "lines_added": 360, "lines_deleted": 44},
        {"type": "session_end", "timestamp": "2026-06-16T03:11:00Z", "status": "completed"},
        {
            "type": "session_start",
            "session_id": "codex-10t-local-max",
            "timestamp": "2026-06-16T04:00:00Z",
            "agent": "codex",
            "model": "future-frontier",
            "model_parameters": {"declared_size": "10T", "context_window": 2000000},
        },
        {"type": "message", "content": "Local-max pass: deepen only the reporting node after global scaffold is stable."},
        {"type": "token_usage", "input_tokens": 1800, "output_tokens": 1250},
        {"type": "tool_call", "tool": "exec_command"},
        {
            "type": "benchmark_result",
            "benchmark": "the-agent-company",
            "task_id": "project-reporting",
            "completed": True,
            "quality_score": 0.91,
            "tests_passed": 18,
            "tests_total": 19,
        },
        {"type": "code_metric", "files_changed": 4, "lines_added": 210, "lines_deleted": 18},
        {"type": "session_end", "timestamp": "2026-06-16T04:07:00Z", "status": "completed"},
    ]
    return build_observation(events)
