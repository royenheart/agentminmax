from pathlib import Path

from agentminmax.aggregation import aggregate_benchmark_runs
from agentminmax.ingest import build_observation, load_jsonl_events


FIXTURES = Path(__file__).parent / "fixtures"


def test_benchmark_runs_are_derived_from_sessions():
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-session.jsonl"), source_id="local")

    runs = aggregate_benchmark_runs(observation.sessions)

    assert len(runs) == 1
    assert runs[0].source_id == "local"
    assert runs[0].benchmark == "swe-bench-verified"
    assert runs[0].run_id == "2026-06-16"
    assert runs[0].task_count == 1
    assert runs[0].session_count == 1
    assert runs[0].completed_count == 1
    assert runs[0].completion_rate == 1.0
    assert runs[0].average_quality_score == 0.82
    assert runs[0].total_tokens == 2000
    assert runs[0].total_tool_calls == 2
    assert runs[0].total_lines_changed == 140


def test_observation_serializes_benchmark_runs_and_sources():
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-session.jsonl"), source_id="local")

    payload = observation.to_dict()

    assert payload["sources"] == []
    assert payload["benchmark_runs"][0]["benchmark"] == "swe-bench-verified"
    assert payload["benchmark_runs"][0]["source_id"] == "local"
