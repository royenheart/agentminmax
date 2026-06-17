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


def test_trace_events_with_session_id_route_to_matching_session():
    events = [
        {"type": "session_start", "session_id": "session-a", "timestamp": "2026-06-16T05:00:00Z"},
        {"type": "session_start", "session_id": "session-b", "timestamp": "2026-06-16T05:01:00Z"},
        {
            "type": "trace_event",
            "session_id": "session-a",
            "timestamp": "2026-06-16T05:02:00Z",
            "category": "message",
            "name": "Assistant stream",
            "phase": "duration",
            "duration_ms": 1000,
        },
    ]

    observation = build_observation(events)

    sessions = {session.session_id: session for session in observation.sessions}
    assert len(sessions["session-a"].trace_events) == 1
    assert len(sessions["session-b"].trace_events) == 0


def test_session_start_enriches_preexisting_trace_only_session():
    events = [
        {
            "type": "trace_event",
            "session_id": "session-a",
            "timestamp": "2026-06-16T05:00:10Z",
            "category": "message",
            "name": "Assistant stream",
        },
        {
            "type": "session_start",
            "session_id": "session-a",
            "timestamp": "2026-06-16T05:00:00Z",
            "agent": "codex",
            "model": "gpt-5-codex",
            "provider": "OpenAI",
        },
    ]

    observation = build_observation(events)

    assert len(observation.sessions) == 1
    session = observation.sessions[0]
    assert session.session_id == "session-a"
    assert session.agent == "codex"
    assert session.model.name == "gpt-5-codex"
    assert session.start_time == "2026-06-16T05:00:00Z"
    assert len(session.trace_events) == 1


def test_native_codex_session_builds_interactive_trace_events():
    events = load_jsonl_events(FIXTURES / "codex-native-session.jsonl")

    observation = build_observation(events)

    session = observation.sessions[0]
    trace_events = session.trace_events
    assert [event.category for event in trace_events] == [
        "message",
        "reasoning",
        "tool",
        "tokens",
        "patch",
        "message",
    ]

    tool_event = next(event for event in trace_events if event.category == "tool")
    assert tool_event.name == "exec_command"
    assert tool_event.phase == "duration"
    assert tool_event.duration_ms == 2000
    assert tool_event.status == "ok"
    assert tool_event.args["cmd"] == "pytest"
    assert "2 passed" in tool_event.output

    reasoning_event = next(event for event in trace_events if event.category == "reasoning")
    assert reasoning_event.name == "Encrypted reasoning"
    assert reasoning_event.detail == "Reasoning content is encrypted by Codex and is not exposed."

    token_event = next(event for event in trace_events if event.category == "tokens")
    assert token_event.tokens["input"] == 1000
    assert token_event.tokens["output"] == 300


def test_native_codex_patch_apply_end_changes_update_code_metrics():
    events = [
        {
            "timestamp": "2026-06-16T05:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": "native-patch-1", "timestamp": "2026-06-16T05:00:00.000Z"},
        },
        {
            "timestamp": "2026-06-16T05:00:10.000Z",
            "type": "event_msg",
            "payload": {
                "type": "patch_apply_end",
                "status": "completed",
                "success": True,
                "call_id": "call_patch",
                "changes": {
                    "src/new.py": {"type": "add", "content": "def new_value():\n    return 1\n"},
                    "src/existing.py": {
                        "type": "update",
                        "unified_diff": "@@ -1 +1 @@\n-old = 1\n+new = 2\n",
                    },
                },
            },
        },
    ]

    observation = build_observation(events)

    session = observation.sessions[0]
    assert session.code.files_changed == 2
    assert session.code.lines_added == 3
    assert session.code.lines_deleted == 1


def test_native_codex_task_lifecycle_becomes_turn_duration_block():
    events = [
        {
            "timestamp": "2026-06-16T05:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": "native-turn-1", "timestamp": "2026-06-16T05:00:00.000Z"},
        },
        {
            "timestamp": "2026-06-16T05:00:05.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "started_at": "2026-06-16T05:00:05.000Z",
            },
        },
        {
            "timestamp": "2026-06-16T05:00:17.500Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-1",
                "completed_at": "2026-06-16T05:00:17.500Z",
                "duration_ms": 12500,
                "time_to_first_token_ms": 2300,
                "last_agent_message": "Done.",
            },
        },
    ]

    observation = build_observation(events)

    lifecycle_events = [event for event in observation.sessions[0].trace_events if event.category == "lifecycle"]
    assert len(lifecycle_events) == 1
    turn_event = lifecycle_events[0]
    assert turn_event.name == "Turn"
    assert turn_event.phase == "duration"
    assert turn_event.timestamp == "2026-06-16T05:00:05.000Z"
    assert turn_event.end_timestamp == "2026-06-16T05:00:17.500Z"
    assert turn_event.duration_ms == 12500
    assert turn_event.args["turn_id"] == "turn-1"
    assert turn_event.args["time_to_first_token_ms"] == 2300
    assert "first token" in turn_event.summary
    assert turn_event.detail == "Done."


def test_native_codex_task_lifecycle_normalizes_numeric_epoch_timestamps():
    events = [
        {
            "timestamp": "2026-06-17T01:35:32.862Z",
            "type": "session_meta",
            "payload": {"id": "native-turn-epoch", "timestamp": "2026-06-17T01:35:32.603Z"},
        },
        {
            "timestamp": "2026-06-17T01:35:32.862Z",
            "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "turn-epoch", "started_at": 1781660132},
        },
        {
            "timestamp": "2026-06-17T01:38:22.824Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-epoch",
                "completed_at": 1781660302,
                "duration_ms": 169579,
            },
        },
    ]

    observation = build_observation(events)

    turn_event = next(event for event in observation.sessions[0].trace_events if event.category == "lifecycle")
    assert turn_event.timestamp == "2026-06-17T01:35:32Z"
    assert turn_event.end_timestamp == "2026-06-17T01:38:22Z"
    assert turn_event.duration_ms == 169579


def test_generic_tool_call_events_become_duration_trace_blocks():
    events = load_jsonl_events(FIXTURES / "codex-session.jsonl")

    observation = build_observation(events)

    trace_events = observation.sessions[0].trace_events
    tool_events = [event for event in trace_events if event.category == "tool"]
    assert [event.name for event in tool_events] == ["exec_command", "apply_patch"]
    assert [event.phase for event in tool_events] == ["duration", "duration"]
    assert [event.duration_ms for event in tool_events] == [300, 120]
