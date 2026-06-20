from pathlib import Path

from agentminmax.ingest import build_observation, load_jsonl_events
from agentminmax.metrics import BENCHMARK_METRICS, SESSION_METRICS
from agentminmax.utils import load_data_json


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


def test_metric_groups_expose_inputs_and_formulas():
    events = load_jsonl_events(FIXTURES / "codex-session.jsonl")

    observation = build_observation(events)

    session = observation.sessions[0]
    groups = {group.group_id: group for group in session.metric_groups}
    llm_metrics = {metric.metric_id: metric for metric in groups["llm"].metrics}
    expansion = llm_metrics["input_output_expansion_ratio"]
    assert expansion.inputs == ["token.output", "token.input"]
    assert expansion.formula == "token.output / token.input"

    benchmark = observation.benchmark_runs[0]
    benchmark_groups = {group.group_id: group for group in benchmark.metric_groups}
    cost_metrics = {metric.metric_id: metric for metric in benchmark_groups["benchmark_cost"].metrics}
    tokens_per_task = cost_metrics["tokens_per_task"]
    assert tokens_per_task.inputs == ["run.total_tokens", "run.task_count"]
    assert tokens_per_task.formula == "run.total_tokens / run.task_count"


def test_complexity_and_model_size_are_exposed_through_metric_framework():
    events = load_jsonl_events(FIXTURES / "codex-session.jsonl")

    observation = build_observation(events)

    session = observation.sessions[0]
    event_names = {event.name for event in session.metric_events}
    assert {
        "model.size_billions",
        "model.absorption",
        "complexity.intrinsic_score",
        "complexity.effective_score",
        "complexity.chaos_score",
    }.issubset(event_names)

    groups = {group.group_id: group for group in session.metric_groups}
    assert {"model", "complexity"}.issubset(groups)
    assert groups["model"].display == {"kind": "cards"}

    model_metrics = {metric.metric_id: metric for metric in groups["model"].metrics}
    assert "model_size_source" not in model_metrics
    assert model_metrics["model_size_billions"].value == 1000
    assert model_metrics["active_model_size_billions"].value == "unknown"
    assert model_metrics["model_absorption"].value == session.complexity.model_absorption
    assert model_metrics["model_size_billions"].formula == "parse(model.parameters.declared_size || model.parameters.size) || fallback(model.name)"
    assert model_metrics["model_size_billions"].labels["source"] == "declared"
    assert model_metrics["model_size_billions"].labels["canonical_model"] == session.model.name

    complexity_metrics = {metric.metric_id: metric for metric in groups["complexity"].metrics}
    assert complexity_metrics["effective_score"].value == session.complexity.effective_score
    assert complexity_metrics["recommended_grain"].value == session.complexity.recommended_grain
    assert complexity_metrics["effective_score"].inputs == ["complexity.intrinsic_score", "model.absorption"]


def test_model_size_falls_back_to_registry_when_session_omits_size():
    events = [
        {
            "type": "session_start",
            "session_id": "fallback-size",
            "timestamp": "2026-06-20T00:00:00Z",
            "agent": "codex",
            "provider": "DeepSeek",
            "model": "DeepSeek-R1",
        },
        {"type": "token_usage_total", "timestamp": "2026-06-20T00:00:01Z", "input_tokens": 100, "output_tokens": 50},
    ]

    observation = build_observation(events)

    session = observation.sessions[0]
    model_events = {event.name: event for event in session.metric_events if event.category == "model"}
    assert model_events["model.size_billions"].value == 671
    assert model_events["model.size_billions"].labels["source"] == "fallback"
    assert model_events["model.size_billions"].labels["canonical_model"] == "deepseek-r1"
    assert model_events["model.size_billions"].labels["confidence"] == "published"
    assert model_events["model.active_size_billions"].value == 37

    groups = {group.group_id: group for group in session.metric_groups}
    model_metrics = {metric.metric_id: metric for metric in groups["model"].metrics}
    assert model_metrics["model_size_billions"].value == 671
    assert model_metrics["active_model_size_billions"].value == 37
    assert "model_size_source" not in model_metrics
    assert model_metrics["model_size_billions"].labels["source"] == "fallback"
    assert model_metrics["model_size_billions"].labels["canonical_model"] == "deepseek-r1"
    assert model_metrics["model_size_billions"].labels["confidence"] == "published"


def test_model_size_fallback_uses_generic_utils_data_loader():
    payload = load_data_json("model_sizes.json")

    assert payload["schema_version"] == 1
    assert any(model["id"] == "deepseek-r1" for model in payload["models"])
    records = {model["id"]: model for model in payload["models"]}
    assert records["gpt-5.5"]["parameter_billions"] == 9700
    assert records["gpt-5.5"]["active_parameter_billions"] is None
    assert records["deepseek-v4-pro"]["parameter_billions"] == 1600
    assert records["deepseek-v4-pro"]["active_parameter_billions"] == 49
    assert records["glm-5.2"]["parameter_billions"] == 744
    assert records["glm-5.2"]["active_parameter_billions"] == 40
    assert records["glm-5.1"]["parameter_billions"] == 744
    assert records["glm-5.1"]["active_parameter_billions"] == 40
    assert not Path("agentminmax/data_loader.py").exists()
    assert not Path("agentminmax/model_registry.py").exists()
    assert "model_registry" not in Path("agentminmax/metrics.py").read_text(encoding="utf-8")


def test_frontier_model_size_fallbacks_are_available_by_alias():
    events = [
        {"type": "session_start", "session_id": "gpt", "timestamp": "2026-06-20T00:00:00Z", "model": "gpt-5.5"},
        {"type": "session_start", "session_id": "deepseek", "timestamp": "2026-06-20T00:01:00Z", "model": "deepseek-v4-pro"},
        {"type": "session_start", "session_id": "glm52", "timestamp": "2026-06-20T00:02:00Z", "model": "glm-5.2[1m]"},
        {"type": "session_start", "session_id": "glm51", "timestamp": "2026-06-20T00:03:00Z", "model": "glm-5.1"},
    ]

    observation = build_observation(events)

    by_session = {session.session_id: session for session in observation.sessions}
    expected = {
        "gpt": (9700, "unknown", "third_party_estimate_disputed"),
        "deepseek": (1600, 49, "published"),
        "glm52": (744, 40, "family_inferred"),
        "glm51": (744, 40, "third_party_estimate"),
    }
    for session_id, (total, active, confidence) in expected.items():
        groups = {group.group_id: group for group in by_session[session_id].metric_groups}
        model_metrics = {metric.metric_id: metric for metric in groups["model"].metrics}
        assert model_metrics["model_size_billions"].value == total
        assert model_metrics["active_model_size_billions"].value == active
        assert model_metrics["model_size_billions"].labels["confidence"] == confidence


def test_complexity_logic_is_not_split_into_legacy_module():
    assert not Path("agentminmax/complexity.py").exists()
    assert "agentminmax.complexity" not in Path("agentminmax/ingest.py").read_text(encoding="utf-8")


def test_metric_definition_ids_are_unique_within_subject():
    session_ids = [definition.metric_id for definition in SESSION_METRICS]
    benchmark_ids = [definition.metric_id for definition in BENCHMARK_METRICS]

    assert len(session_ids) == len(set(session_ids))
    assert len(benchmark_ids) == len(set(benchmark_ids))


def test_session_metric_definitions_do_not_repeat_same_formula_and_inputs_across_groups():
    by_formula_inputs = {}
    for definition in SESSION_METRICS:
        key = (definition.formula, tuple(definition.inputs))
        if not definition.formula:
            continue
        assert key not in by_formula_inputs, (
            f"{definition.group_id}.{definition.metric_id} repeats "
            f"{by_formula_inputs[key].group_id}.{by_formula_inputs[key].metric_id}"
        )
        by_formula_inputs[key] = definition


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


def test_build_observation_exposes_metric_events_and_groups():
    events = [
        {
            "type": "session_start",
            "session_id": "metric-session",
            "timestamp": "2026-06-16T05:00:00Z",
            "agent": "codex",
            "model": "gpt-5-codex",
            "model_parameters": {"declared_size": "1T", "context_window": 2000},
        },
        {
            "type": "message",
            "timestamp": "2026-06-16T05:00:01Z",
            "role": "user",
            "content": "Implement the parser and run tests.",
        },
        {"type": "token_usage_total", "timestamp": "2026-06-16T05:00:02Z", "input_tokens": 1000, "output_tokens": 250, "cached_input_tokens": 100},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:03Z", "tool": "exec_command"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:04Z", "tool": "apply_patch"},
        {
            "type": "trace_event",
            "timestamp": "2026-06-16T05:00:04Z",
            "category": "tool",
            "name": "apply_patch",
            "status": "error",
            "summary": "apply_patch verification failed",
        },
        {"type": "code_metric", "timestamp": "2026-06-16T05:00:05Z", "files_changed": 2, "lines_added": 20, "lines_deleted": 5},
        {
            "type": "benchmark_result",
            "timestamp": "2026-06-16T05:00:06Z",
            "benchmark": "HumanEval-lite",
            "task_id": "task-1",
            "completed": True,
            "quality_score": 1.0,
            "tests_passed": 3,
            "tests_total": 3,
        },
        {"type": "session_end", "session_id": "metric-session", "timestamp": "2026-06-16T05:01:42Z", "status": "completed"},
    ]

    observation = build_observation(events)

    session = observation.sessions[0]
    event_names = {event.name for event in session.metric_events}
    assert {"token.input", "tool.call", "code.lines_changed", "benchmark.task_result"}.issubset(event_names)

    groups = {group.group_id: group for group in session.metric_groups}
    assert {"intent", "llm", "agent_behavior", "planning", "engineering", "benchmark"}.issubset(groups)
    assert groups["agent_behavior"].label == "Tools And Calls"
    assert groups["agent_behavior"].display == {"kind": "bars"}
    assert groups["llm"].display == {"kind": "cards"}

    behavior_metrics = {metric.metric_id: metric.value for metric in groups["agent_behavior"].metrics}
    assert behavior_metrics["tool_call_count"] == 2
    assert behavior_metrics["tool_error_count"] == 1
    assert behavior_metrics["tool_success_rate"] == 0.5

    llm_metrics = {metric.metric_id: metric.value for metric in groups["llm"].metrics}
    assert llm_metrics["context_utilization"] == 0.5
    assert llm_metrics["input_output_expansion_ratio"] == 0.25
    assert llm_metrics["cache_hit_ratio"] == 0.1

    intent_metrics = {metric.metric_id: metric.value for metric in groups["intent"].metrics}
    assert intent_metrics["intent_kind"] == "implementation"
    assert intent_metrics["expected_artifact"] == "code_patch"


def test_benchmark_runs_expose_metric_groups():
    events = [
        {
            "type": "session_start",
            "session_id": "bench-metric-session",
            "timestamp": "2026-06-16T05:00:00Z",
            "source_id": "runs",
            "run_id": "run-1",
        },
        {"type": "token_usage_total", "timestamp": "2026-06-16T05:00:02Z", "input_tokens": 900, "output_tokens": 100},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:03Z", "tool": "exec_command"},
        {"type": "code_metric", "timestamp": "2026-06-16T05:00:05Z", "files_changed": 1, "lines_added": 8, "lines_deleted": 2},
        {
            "type": "benchmark_result",
            "timestamp": "2026-06-16T05:00:06Z",
            "source_id": "runs",
            "benchmark": "HumanEval-lite",
            "task_id": "task-1",
            "completed": True,
            "quality_score": 1.0,
            "tests_passed": 3,
            "tests_total": 3,
            "duration_seconds": 12,
        },
        {"type": "session_end", "session_id": "bench-metric-session", "timestamp": "2026-06-16T05:01:00Z", "status": "completed"},
    ]

    observation = build_observation(events)

    run = observation.benchmark_runs[0]
    groups = {group.group_id: group for group in run.metric_groups}
    assert {"benchmark_quality", "benchmark_cost"}.issubset(groups)
    assert groups["benchmark_quality"].display == {"kind": "bars"}
    assert groups["benchmark_cost"].display == {"kind": "bars"}

    quality_metrics = {metric.metric_id: metric.value for metric in groups["benchmark_quality"].metrics}
    assert quality_metrics["pass_rate"] == 1.0

    cost_metrics = {metric.metric_id: metric.value for metric in groups["benchmark_cost"].metrics}
    assert cost_metrics["tokens_per_task"] == 1000
    assert cost_metrics["tool_calls_per_task"] == 1
    assert cost_metrics["lines_changed_per_task"] == 10


def test_session_research_metrics_capture_dag_entropy_and_local_optimum_signals():
    events = [
        {
            "type": "session_start",
            "session_id": "research-session",
            "timestamp": "2026-06-16T05:00:00Z",
            "agent": "codex",
            "model": "gpt-5-codex",
        },
        {
            "type": "message",
            "timestamp": "2026-06-16T05:00:01Z",
            "role": "user",
            "content": "Research and implement a parser. Then run tests.",
        },
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:02Z", "tool": "rg"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:03Z", "tool": "rg"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:04Z", "tool": "sed"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:05Z", "tool": "apply_patch"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:06Z", "tool": "exec_command"},
        {
            "type": "trace_event",
            "timestamp": "2026-06-16T05:00:07Z",
            "category": "tool",
            "name": "update_plan",
            "args": {
                "plan": [
                    {"step": "Design metric graph", "status": "completed"},
                    {"step": "Implement parser", "status": "in_progress"},
                    {"step": "Render dashboard", "status": "pending"},
                    {"step": "Verify tests", "status": "pending"},
                ]
            },
        },
        {
            "type": "trace_event",
            "timestamp": "2026-06-16T05:00:08Z",
            "category": "tool",
            "name": "apply_patch",
            "status": "error",
            "summary": "apply_patch verification failed",
        },
        {
            "type": "trace_event",
            "timestamp": "2026-06-16T05:00:09Z",
            "category": "tool",
            "name": "exec_command",
            "status": "error",
            "summary": "Process exited with code 1",
        },
        {"type": "code_metric", "timestamp": "2026-06-16T05:00:10Z", "files_changed": 2, "lines_added": 40, "lines_deleted": 10},
        {
            "type": "benchmark_result",
            "timestamp": "2026-06-16T05:00:11Z",
            "benchmark": "Synthetic",
            "task_id": "case-1",
            "completed": False,
            "quality_score": 0.25,
            "tests_passed": 1,
            "tests_total": 4,
        },
    ]

    observation = build_observation(events)

    session = observation.sessions[0]
    event_names = {event.name for event in session.metric_events}
    assert {"plan.update", "chaos.tool_entropy", "output.code_density"}.issubset(event_names)

    groups = {group.group_id: group for group in session.metric_groups}
    assert {"dag", "chaos", "local_optimum"}.issubset(groups)

    dag_metrics = {metric.metric_id: metric.value for metric in groups["dag"].metrics}
    assert dag_metrics["dag_width_proxy"] == 4
    assert dag_metrics["leaf_pending_ratio"] == 0.5

    chaos_metrics = {metric.metric_id: metric.value for metric in groups["chaos"].metrics}
    assert chaos_metrics["tool_entropy"] > 0
    assert chaos_metrics["error_pressure"] == 0.4

    local_metrics = {metric.metric_id: metric.value for metric in groups["local_optimum"].metrics}
    assert local_metrics["exploration_to_edit_ratio"] == 3.0
    assert local_metrics["effective_output_density"] == 10.0


def test_benchmark_research_metrics_capture_variance_and_depth_costs():
    events = [
        {"type": "session_start", "session_id": "bench-a", "timestamp": "2026-06-16T05:00:00Z", "source_id": "runs", "run_id": "run-2"},
        {"type": "token_usage_total", "timestamp": "2026-06-16T05:00:01Z", "input_tokens": 100, "output_tokens": 50},
        {"type": "tool_call", "timestamp": "2026-06-16T05:00:02Z", "tool": "exec_command"},
        {"type": "benchmark_result", "timestamp": "2026-06-16T05:00:03Z", "source_id": "runs", "benchmark": "Synthetic", "task_id": "case-a", "completed": True, "quality_score": 1.0, "tests_passed": 4, "tests_total": 4},
        {"type": "session_start", "session_id": "bench-b", "timestamp": "2026-06-16T05:01:00Z", "source_id": "runs", "run_id": "run-2"},
        {"type": "token_usage_total", "timestamp": "2026-06-16T05:01:01Z", "input_tokens": 200, "output_tokens": 100},
        {"type": "tool_call", "timestamp": "2026-06-16T05:01:02Z", "tool": "exec_command"},
        {"type": "tool_call", "timestamp": "2026-06-16T05:01:03Z", "tool": "apply_patch"},
        {"type": "benchmark_result", "timestamp": "2026-06-16T05:01:04Z", "source_id": "runs", "benchmark": "Synthetic", "task_id": "case-b", "completed": False, "quality_score": 0.0, "tests_passed": 0, "tests_total": 4},
    ]

    observation = build_observation(events)

    run = observation.benchmark_runs[0]
    groups = {group.group_id: group for group in run.metric_groups}
    assert "benchmark_stability" in groups

    stability_metrics = {metric.metric_id: metric.value for metric in groups["benchmark_stability"].metrics}
    assert stability_metrics["completion_variance_proxy"] == 0.25
    assert stability_metrics["average_tokens_per_session"] == 225
    assert stability_metrics["depth_cost_proxy"] == 1.5
