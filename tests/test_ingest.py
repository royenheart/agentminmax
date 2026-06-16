from pathlib import Path

from agentminmax.ingest import build_observation, load_jsonl_events


FIXTURES = Path(__file__).parent / "fixtures"


def test_build_observation_aggregates_codex_session_metrics():
    events = load_jsonl_events(FIXTURES / "codex-session.jsonl")

    observation = build_observation(events)

    assert observation.summary.session_count == 1
    assert observation.summary.total_tokens == 2000
    assert observation.summary.total_tool_calls == 2
    assert observation.summary.total_lines_changed == 140
    assert observation.summary.benchmark_completion_rate == 1.0

    session = observation.sessions[0]
    assert session.session_id == "codex-demo-1"
    assert session.agent == "codex"
    assert session.model.name == "gpt-5-codex"
    assert session.model.parameters["declared_size"] == "1T"
    assert session.duration_seconds == 330
    assert session.tokens.input == 1200
    assert session.tokens.output == 800
    assert session.tool_calls["exec_command"] == 1
    assert session.tool_calls["apply_patch"] == 1
    assert session.code.files_changed == 4
    assert session.benchmarks[0].benchmark == "swe-bench-verified"


def test_build_observation_computes_relative_complexity_by_model_size():
    events = load_jsonl_events(FIXTURES / "codex-session.jsonl")

    observation = build_observation(events)

    session = observation.sessions[0]
    assert session.complexity.intrinsic_score > 0
    assert 0 < session.complexity.model_absorption < 1
    assert session.complexity.effective_score < session.complexity.intrinsic_score
    assert session.complexity.recommended_grain in {"coarse", "medium", "fine"}


def test_build_observation_accepts_native_codex_session_schema():
    events = load_jsonl_events(FIXTURES / "codex-native-session.jsonl")

    observation = build_observation(events)

    session = observation.sessions[0]
    assert session.session_id == "native-1"
    assert session.agent == "codex-tui"
    assert session.model.provider == "OpenAI"
    assert session.model.name == "gpt-5.4"
    assert session.model.parameters["context_window"] == 950000
    assert session.model.parameters["cli_version"] == "0.130.0"
    assert session.duration_seconds == 40
    assert session.tokens.input == 1000
    assert session.tokens.output == 300
    assert session.tokens.cached_input == 200
    assert session.tool_calls["exec_command"] == 1
    assert "Collect observability metrics." in session.logs
    assert "Metrics collected." in session.logs


def test_native_codex_session_preserves_source_id_from_loader():
    events = load_jsonl_events(FIXTURES / "codex-native-session.jsonl")
    for event in events:
        event["source_id"] = "local-codex"

    observation = build_observation(events)

    assert observation.sessions[0].source_id == "local-codex"
