from __future__ import annotations

## @file
# @brief Event and metric derivation for AgentMinMax observability.
#
# Raw Codex or benchmark events are normalized by `agentminmax.ingest`,
# aggregated into `AgentSession` and `BenchmarkRun` models, then enriched here
# with atomic events and grouped metrics. Dashboard cards and generated
# documentation read the same `MetricDefinition` and `MetricEventDefinition`
# data so metric meaning, inputs, and formulas stay close to the code that
# computes them.

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agentminmax.models import AgentSession, BenchmarkRun, ComplexityMetrics, MetricEvent, MetricGroup, MetricValue
from agentminmax.utils import load_data_json

"""! @brief Event and metric derivation for AgentMinMax observability.

@details This module is the source of truth for dashboard observability metrics.
Raw Codex or benchmark events are normalized by `agentminmax.ingest`, aggregated
into `AgentSession` and `BenchmarkRun` models, then enriched here with atomic
events and grouped metrics. Dashboard cards and generated documentation read the
same `MetricDefinition` and `MetricEventDefinition` data so metric meaning,
inputs, and formulas stay close to the code that computes them.
"""


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """! @brief Declarative definition for one dashboard metric.

    @details The `compute` callback reads an `AgentSession` or `BenchmarkRun`.
    The surrounding fields document how that value is interpreted: `inputs`
    names the normalized events or model fields consumed by the metric, while
    `formula` gives the calculation shown in dashboard detail views and generated
    docs.
    """

    metric_id: str
    label: str
    group_id: str
    group_label: str
    unit: str
    description: str
    compute: Callable[[Any], float | int | str | None]
    formula: str = ""
    inputs: tuple[str, ...] = ()
    display: dict[str, Any] | None = None
    labels: Callable[[Any], dict[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class MetricEventDefinition:
    """! @brief Documentation metadata for one atomic observation event.

    @details Atomic events are lower-level facts extracted from session state,
    trace events, benchmark results, or model metadata. Grouped metrics either
    reuse these events directly or combine them into higher-level ratios,
    scores, and proxies.
    """

    name: str
    category: str
    unit: str
    source: str
    description: str
    formula: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelSizeInfo:
    parameter_billions: float
    active_parameter_billions: float | None
    source: str
    canonical_model: str
    confidence: str
    raw_size: str
    architecture: str
    source_url: str = ""


@dataclass(frozen=True, slots=True)
class ModelSizeRecord:
    id: str
    provider: str
    aliases: tuple[str, ...]
    parameter_billions: float | None
    active_parameter_billions: float | None
    architecture: str
    confidence: str
    source: str
    source_url: str


def enrich_session_metrics(session: AgentSession) -> None:
    """! @brief Attach complexity, atomic events, and grouped metrics to a session."""

    session.complexity = _compute_complexity(session)
    session.metric_events = session_metric_events(session)
    session.metric_groups = _groups_from_definitions(session, SESSION_METRICS)


def enrich_benchmark_metrics(run: BenchmarkRun) -> None:
    """! @brief Attach grouped metrics to an aggregated benchmark run."""

    run.metric_groups = _groups_from_definitions(run, BENCHMARK_METRICS)


def session_metric_events(session: AgentSession) -> list[MetricEvent]:
    """! @brief Convert an enriched session into atomic metric events.

    @details These events are intentionally close to the normalized observation
    model: token events come from token counters, tool events from trace/tool
    aggregation, code events from structured patch metrics, and benchmark events
    from task results. They are useful as trace-aligned facts and as the input
    vocabulary for higher-level grouped metrics.
    """

    complexity = session.complexity or _compute_complexity(session)
    model_size = _model_size_info(session)
    events = [
        MetricEvent(
            "model.size_billions",
            model_size.parameter_billions,
            unit="B",
            category="model",
            labels=_model_size_labels(model_size),
        ),
        MetricEvent(
            "model.absorption",
            _model_absorption(session),
            unit="ratio",
            category="model",
            labels={"source": model_size.source, "canonical_model": model_size.canonical_model},
        ),
        MetricEvent(
            "complexity.intrinsic_score",
            complexity.intrinsic_score,
            unit="score",
            category="complexity",
        ),
        MetricEvent(
            "complexity.effective_score",
            complexity.effective_score,
            unit="score",
            category="complexity",
        ),
        MetricEvent(
            "complexity.chaos_score",
            complexity.chaos_score,
            unit="score",
            category="complexity",
        ),
        MetricEvent("token.input", session.tokens.input, unit="tokens", category="llm", timestamp=session.end_time),
        MetricEvent("token.output", session.tokens.output, unit="tokens", category="llm", timestamp=session.end_time),
        MetricEvent(
            "token.cached_input",
            session.tokens.cached_input,
            unit="tokens",
            category="llm",
            timestamp=session.end_time,
        ),
        MetricEvent("code.files_changed", session.code.files_changed, unit="files", category="engineering"),
        MetricEvent("code.lines_added", session.code.lines_added, unit="lines", category="engineering"),
        MetricEvent("code.lines_deleted", session.code.lines_deleted, unit="lines", category="engineering"),
        MetricEvent("code.lines_changed", session.code.lines_changed, unit="lines", category="engineering"),
        MetricEvent("benchmark.task_result", len(session.benchmarks), unit="tasks", category="benchmark"),
    ]
    if model_size.active_parameter_billions is not None:
        events.append(
            MetricEvent(
                "model.active_size_billions",
                model_size.active_parameter_billions,
                unit="B",
                category="model",
                labels=_model_size_labels(model_size),
            )
        )
    for tool, count in sorted(session.tool_calls.items()):
        events.append(
            MetricEvent(
                "tool.call",
                count,
                unit="calls",
                category="agent_behavior",
                timestamp=session.end_time,
                labels={"tool": tool},
            )
        )
    error_count = _tool_error_count(session)
    if error_count:
        events.append(MetricEvent("tool.error", error_count, unit="calls", category="agent_behavior"))
    plan_updates = _plan_update_count(session)
    if plan_updates:
        events.append(MetricEvent("plan.update", plan_updates, unit="updates", category="planning"))
    events.append(MetricEvent("chaos.tool_entropy", _tool_entropy(session), unit="bits", category="chaos"))
    events.append(MetricEvent("output.code_density", _effective_output_density(session), unit="lines/call", category="local_optimum"))
    return events


def _groups_from_definitions(subject: Any, definitions: list[MetricDefinition]) -> list[MetricGroup]:
    groups: dict[str, MetricGroup] = {}
    for definition in definitions:
        value = definition.compute(subject)
        if value is None:
            continue
        group = groups.setdefault(
            definition.group_id,
            MetricGroup(
                group_id=definition.group_id,
                label=definition.group_label,
                display=dict(definition.display or {"kind": "cards"}),
            ),
        )
        group.metrics.append(
            MetricValue(
                metric_id=definition.metric_id,
                label=definition.label,
                value=value,
                unit=definition.unit,
                description=definition.description,
                formula=definition.formula,
                inputs=list(definition.inputs),
                labels=definition.labels(subject) if definition.labels else {},
            )
        )
    return list(groups.values())


def _metric(
    metric_id: str,
    label: str,
    group_id: str,
    group_label: str,
    unit: str,
    description: str,
    compute: Callable[[Any], float | int | str | None],
    *,
    formula: str = "",
    inputs: tuple[str, ...] | list[str] = (),
    display: dict[str, Any] | None = None,
    labels: Callable[[Any], dict[str, Any]] | None = None,
) -> MetricDefinition:
    return MetricDefinition(metric_id, label, group_id, group_label, unit, description, compute, formula, tuple(inputs), display, labels)


def _raw_model_size(parameters: dict[str, Any]) -> str:
    return str(parameters.get("declared_size") or parameters.get("size") or "").strip()


def _model_size_info(session: AgentSession) -> ModelSizeInfo:
    raw_size = _raw_model_size(session.model.parameters)
    declared_billions = _parse_model_size_to_billions(raw_size)
    if declared_billions > 0:
        return ModelSizeInfo(
            parameter_billions=declared_billions,
            active_parameter_billions=None,
            source="declared",
            canonical_model=session.model.name or "unknown",
            confidence="declared",
            raw_size=raw_size,
            architecture="unknown",
        )

    record = _lookup_model_size(session.model.name)
    if record and record.parameter_billions is not None:
        return _model_size_info_from_record(record, raw_size)

    return ModelSizeInfo(
        parameter_billions=0.0,
        active_parameter_billions=None,
        source="unknown",
        canonical_model=session.model.name or "unknown",
        confidence="unknown",
        raw_size=raw_size,
        architecture="unknown",
    )


def _model_size_info_from_record(record: ModelSizeRecord, raw_size: str) -> ModelSizeInfo:
    return ModelSizeInfo(
        parameter_billions=float(record.parameter_billions or 0.0),
        active_parameter_billions=record.active_parameter_billions,
        source="fallback",
        canonical_model=record.id,
        confidence=record.confidence,
        raw_size=raw_size,
        architecture=record.architecture,
        source_url=record.source_url,
    )


def _model_size_labels(info: ModelSizeInfo) -> dict[str, Any]:
    labels = {
        "raw_size": info.raw_size,
        "source": info.source,
        "canonical_model": info.canonical_model,
        "confidence": info.confidence,
        "architecture": info.architecture,
    }
    if info.source_url:
        labels["source_url"] = info.source_url
    return labels


def _model_size_metric_labels(session: AgentSession) -> dict[str, Any]:
    return _model_size_labels(_model_size_info(session))


def _model_size_billions(session: AgentSession) -> float:
    return _model_size_info(session).parameter_billions


def _active_model_size_billions(session: AgentSession) -> float | str:
    return _model_size_info(session).active_parameter_billions or "unknown"


def _model_absorption(session: AgentSession) -> float:
    return _estimate_model_absorption_from_billions(_model_size_billions(session))


def _estimate_model_absorption_from_billions(billions: float) -> float:
    if billions <= 0:
        return 0.25
    if billions < 70:
        return 0.18
    if billions < 300:
        return 0.32
    if billions < 1000:
        return 0.45
    if billions < 3000:
        return 0.58
    return 0.70


def _compute_complexity(session: AgentSession) -> ComplexityMetrics:
    """! @brief Estimate task complexity before and after model-size absorption.

    @details Intrinsic complexity combines token volume, tool count, tool
    diversity, benchmark pressure, code churn, quality gaps, and wall-clock
    duration. Model absorption is a coarse piecewise estimate from model scale.
    Effective complexity is the remaining work after absorption and is bucketed
    into the recommended goal grain.
    """

    tool_total = sum(session.tool_calls.values())
    unique_tools = len(session.tool_calls)
    benchmark_count = len(session.benchmarks)
    failed_benchmarks = sum(1 for result in session.benchmarks if not result.completed)
    quality_gap = 0.0
    if session.benchmarks:
        quality_gap = sum(1.0 - result.quality_score for result in session.benchmarks)

    intrinsic = (
        math.log1p(session.tokens.total) / 2.0
        + 1.35 * tool_total
        + 0.55 * unique_tools
        + 1.75 * benchmark_count
        + 2.5 * failed_benchmarks
        + 2.0 * quality_gap
        + 0.02 * session.code.lines_changed
        + 0.004 * max(session.duration_seconds, 0)
    )
    absorption = _model_absorption(session)
    effective = max(intrinsic * (1.0 - absorption), 0.0)
    if effective >= 14:
        grain = "fine"
    elif effective >= 7:
        grain = "medium"
    else:
        grain = "coarse"

    chaos = max(0.0, failed_benchmarks + 0.01 * session.code.lines_deleted + 0.25 * quality_gap)
    return ComplexityMetrics(
        intrinsic_score=round(intrinsic, 3),
        model_absorption=round(absorption, 3),
        effective_score=round(effective, 3),
        recommended_grain=grain,
        chaos_score=round(chaos, 3),
    )


def _parse_model_size_to_billions(raw_size: str) -> float:
    if not raw_size:
        return 0.0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([bBtT])", raw_size)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2).lower()
    return value * 1000.0 if unit == "t" else value


def _lookup_model_size(model_name: str) -> ModelSizeRecord | None:
    key = _normalize_model_name(model_name)
    if not key:
        return None
    for record in _model_size_records():
        names = (record.id, *record.aliases)
        if key in {_normalize_model_name(name) for name in names}:
            return record
    return None


def _model_size_records() -> tuple[ModelSizeRecord, ...]:
    return tuple(_model_size_record(item) for item in load_data_json("model_sizes.json").get("models", []))


def _model_size_record(item: dict[str, Any]) -> ModelSizeRecord:
    return ModelSizeRecord(
        id=str(item["id"]),
        provider=str(item.get("provider", "unknown")),
        aliases=tuple(str(alias) for alias in item.get("aliases", [])),
        parameter_billions=_optional_float(item.get("parameter_billions")),
        active_parameter_billions=_optional_float(item.get("active_parameter_billions")),
        architecture=str(item.get("architecture", "unknown")),
        confidence=str(item.get("confidence", "unknown")),
        source=str(item.get("source", "")),
        source_url=str(item.get("source_url", "")),
    )


def _normalize_model_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _intent_text(session: AgentSession) -> str:
    return " ".join(session.logs[:6]).lower()


def _intent_kind(session: AgentSession) -> str:
    text = _intent_text(session)
    if re.search(r"(只读|不要修改|do not edit|do not modify|read[- ]?only|静态审查)", text, re.I):
        return "read_only"
    if session.code.files_changed or session.code.lines_changed:
        return "implementation"
    if session.benchmarks:
        return "benchmark_run"
    if re.search(r"(review|审查|audit)", text, re.I):
        return "review"
    if re.search(r"(debug|root cause|根因|修复|fix)", text, re.I):
        return "debugging"
    if re.search(r"(research|调研|方案|design|plan)", text, re.I):
        return "research"
    return "unknown"


def _session_complexity(session: AgentSession) -> ComplexityMetrics:
    if session.complexity is None:
        session.complexity = _compute_complexity(session)
    return session.complexity


def _expected_artifact(session: AgentSession) -> str:
    intent = _intent_kind(session)
    if session.code.files_changed or session.code.lines_changed or intent == "implementation":
        return "code_patch"
    if session.benchmarks:
        return "benchmark_result"
    if intent in {"read_only", "review", "research", "debugging"}:
        return "report"
    return "unknown"


def _model_normalized_grain(session: AgentSession) -> float:
    return round(float(_session_complexity(session).effective_score), 4)


def _context_utilization(session: AgentSession) -> float:
    context_window = int(session.model.parameters.get("context_window") or 0)
    if context_window <= 0:
        return 0.0
    return round(session.tokens.input / context_window, 4)


def _input_output_expansion_ratio(session: AgentSession) -> float:
    if session.tokens.input <= 0:
        return 0.0
    return round(session.tokens.output / session.tokens.input, 4)


def _cache_hit_ratio(session: AgentSession) -> float:
    if session.tokens.input <= 0:
        return 0.0
    return round(session.tokens.cached_input / session.tokens.input, 4)


def _tokens_per_second(session: AgentSession) -> float:
    if session.duration_seconds <= 0:
        return 0.0
    return round(session.tokens.total / session.duration_seconds, 4)


def _tool_error_count(session: AgentSession) -> int:
    errors = 0
    for event in session.trace_events:
        if event.category != "tool" and event.lane not in {"Tool Calls", "MCP Calls"}:
            continue
        text = f"{event.summary}\n{event.detail}\n{event.output}".lower()
        if event.status == "error" or "verification failed" in text or "process exited with code 1" in text:
            errors += 1
    return min(errors, sum(session.tool_calls.values())) if session.tool_calls else errors


def _tool_success_rate(session: AgentSession) -> float:
    total = sum(session.tool_calls.values())
    if total <= 0:
        return 1.0
    return round(max(total - _tool_error_count(session), 0) / total, 4)


def _retry_ratio(session: AgentSession) -> float:
    total = sum(session.tool_calls.values())
    if total <= 0:
        return 0.0
    repeated = sum(max(count - 1, 0) for count in session.tool_calls.values())
    return round(repeated / total, 4)


def _patch_failure_count(session: AgentSession) -> int:
    failures = 0
    for event in session.trace_events:
        text = f"{event.name}\n{event.summary}\n{event.detail}\n{event.output}".lower()
        if "patch" not in text and event.name != "apply_patch":
            continue
        if event.status == "error" or "verification failed" in text or "patch failed" in text:
            failures += 1
    return failures


def _plan_width_proxy(session: AgentSession) -> int:
    width = 0
    for event in session.trace_events:
        if event.name != "update_plan":
            continue
        plan = event.args.get("plan")
        if isinstance(plan, list):
            width = max(width, len(plan))
    return width


def _plan_update_count(session: AgentSession) -> int:
    trace_updates = sum(1 for event in session.trace_events if event.name == "update_plan")
    return max(int(session.tool_calls.get("update_plan", 0)), trace_updates)


def _plan_status_counts(session: AgentSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    latest_plan: list[dict[str, Any]] = []
    for event in session.trace_events:
        if event.name != "update_plan":
            continue
        plan = event.args.get("plan")
        if isinstance(plan, list):
            latest_plan = [item for item in plan if isinstance(item, dict)]
    for item in latest_plan:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _leaf_pending_ratio(session: AgentSession) -> float:
    width = _plan_width_proxy(session)
    if width <= 0:
        return 0.0
    counts = _plan_status_counts(session)
    pending = counts.get("pending", 0)
    return round(pending / width, 4)


def _plan_churn_proxy(session: AgentSession) -> float:
    updates = _plan_update_count(session)
    width = _plan_width_proxy(session)
    if updates <= 0 or width <= 0:
        return 0.0
    return round(updates / width, 4)


def _churn_proxy(session: AgentSession) -> float:
    changed = session.code.lines_changed
    if changed <= 0:
        return 0.0
    return round(session.code.lines_deleted / changed, 4)


def _test_pass_rate(session: AgentSession) -> float:
    total = sum(result.tests_total for result in session.benchmarks)
    if total <= 0:
        return 0.0
    passed = sum(result.tests_passed for result in session.benchmarks)
    return round(passed / total, 4)


def _session_benchmark_completion_rate(session: AgentSession) -> float:
    if not session.benchmarks:
        return 0.0
    completed = sum(1 for result in session.benchmarks if result.completed)
    return round(completed / len(session.benchmarks), 4)


def _session_benchmark_quality(session: AgentSession) -> float:
    if not session.benchmarks:
        return 0.0
    return round(sum(result.quality_score for result in session.benchmarks) / len(session.benchmarks), 4)


def _tool_entropy(session: AgentSession) -> float:
    total = sum(session.tool_calls.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in session.tool_calls.values():
        if count <= 0:
            continue
        probability = count / total
        entropy -= probability * math.log2(probability)
    return round(entropy, 4)


def _error_pressure(session: AgentSession) -> float:
    total = sum(session.tool_calls.values())
    if total <= 0:
        return 0.0
    return round(_tool_error_count(session) / total, 4)


def _exploration_tool_count(session: AgentSession) -> int:
    exploration_names = {
        "rg",
        "grep",
        "find",
        "sed",
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "jq",
        "sqlite3",
    }
    count = 0
    for tool, value in session.tool_calls.items():
        if tool in exploration_names:
            count += value
    return count


def _edit_tool_count(session: AgentSession) -> int:
    edit_names = {
        "apply_patch",
        "create_file",
        "update_file",
        "delete_file",
        "write_file",
    }
    count = 0
    for tool, value in session.tool_calls.items():
        if tool in edit_names:
            count += value
    return count


def _exploration_to_edit_ratio(session: AgentSession) -> float:
    edits = _edit_tool_count(session)
    if edits <= 0:
        return float(_exploration_tool_count(session))
    return round(_exploration_tool_count(session) / edits, 4)


def _effective_output_density(session: AgentSession) -> float:
    total_tools = sum(session.tool_calls.values())
    if total_tools <= 0:
        return 0.0
    return round(session.code.lines_changed / total_tools, 4)


def _local_optimum_signal(session: AgentSession) -> float:
    if not session.benchmarks:
        return 0.0
    quality_gap = 1.0 - _session_benchmark_quality(session)
    exploration_pressure = min(_exploration_to_edit_ratio(session) / 10, 1.0)
    retry_pressure = min(_retry_ratio(session), 1.0)
    return round((quality_gap + exploration_pressure + retry_pressure) / 3, 4)


def _run_tokens_per_task(run: BenchmarkRun) -> float:
    return _divide(run.total_tokens, run.task_count)


def _run_tool_calls_per_task(run: BenchmarkRun) -> float:
    return _divide(run.total_tool_calls, run.task_count)


def _run_duration_per_task(run: BenchmarkRun) -> float:
    return _divide(run.total_duration_seconds, run.task_count)


def _run_lines_changed_per_task(run: BenchmarkRun) -> float:
    return _divide(run.total_lines_changed, run.task_count)


def _run_cost_per_pass(run: BenchmarkRun) -> float:
    return _divide(run.total_tokens, run.completed_count)


def _run_sessions_per_task(run: BenchmarkRun) -> float:
    return _divide(run.session_count, run.task_count)


def _run_completion_variance_proxy(run: BenchmarkRun) -> float:
    rate = max(min(run.completion_rate, 1.0), 0.0)
    return round(rate * (1 - rate), 4)


def _run_average_tokens_per_session(run: BenchmarkRun) -> float:
    return _divide(run.total_tokens, run.session_count)


def _run_depth_cost_proxy(run: BenchmarkRun) -> float:
    return _divide(run.total_tool_calls, run.session_count)


def _divide(numerator: float | int, denominator: float | int) -> float:
    if denominator <= 0:
        return 0.0
    result = numerator / denominator
    return int(result) if float(result).is_integer() else round(result, 4)


ATOMIC_EVENT_DEFINITIONS: tuple[MetricEventDefinition, ...] = (
    MetricEventDefinition(
        "model.size_billions",
        "model",
        "B",
        "session.model.parameters.declared_size, session.model.parameters.size, or agentminmax/data/model_sizes.json",
        "Model scale normalized to billions of parameters.",
        "parse(model.parameters.declared_size || model.parameters.size) || fallback(model.name)",
        ("raw_size", "source", "canonical_model", "confidence", "architecture"),
    ),
    MetricEventDefinition(
        "model.active_size_billions",
        "model",
        "B",
        "agentminmax/data/model_sizes.json",
        "Activated parameter count for mixture-of-experts models when known.",
        "fallback(model.name).active_parameter_billions",
        ("raw_size", "source", "canonical_model", "confidence", "architecture"),
    ),
    MetricEventDefinition(
        "model.absorption",
        "model",
        "ratio",
        "model.size_billions",
        "Coarse estimate of the task complexity absorbed by model scale.",
        "piecewise(model.size_billions)",
        ("source", "canonical_model"),
    ),
    MetricEventDefinition(
        "complexity.intrinsic_score",
        "complexity",
        "score",
        "tokens, tools, benchmark results, code metrics, and duration_seconds",
        "Task complexity before model absorption.",
        "log1p(tokens.total)/2 + tool/benchmark/code/time pressure terms",
    ),
    MetricEventDefinition(
        "complexity.effective_score",
        "complexity",
        "score",
        "complexity.intrinsic_score and model.absorption",
        "Complexity remaining after model-size absorption.",
        "complexity.intrinsic_score * (1 - model.absorption)",
    ),
    MetricEventDefinition(
        "complexity.chaos_score",
        "complexity",
        "score",
        "benchmark failures, code.lines_deleted, and benchmark quality gap",
        "Proxy for unstable iteration and regression pressure.",
        "failed_benchmarks + 0.01*code.lines_deleted + 0.25*quality_gap",
    ),
    MetricEventDefinition("token.input", "llm", "tokens", "token_usage/token_usage_total events", "Input tokens consumed by the session."),
    MetricEventDefinition("token.output", "llm", "tokens", "token_usage/token_usage_total events", "Output tokens produced by the session."),
    MetricEventDefinition(
        "token.cached_input",
        "llm",
        "tokens",
        "token_usage/token_usage_total events",
        "Input tokens served from model/provider cache when reported.",
    ),
    MetricEventDefinition("code.files_changed", "engineering", "files", "code_metric or Codex patch_apply_end events", "Changed file count."),
    MetricEventDefinition("code.lines_added", "engineering", "lines", "code_metric or Codex patch_apply_end events", "Added line count."),
    MetricEventDefinition("code.lines_deleted", "engineering", "lines", "code_metric or Codex patch_apply_end events", "Deleted line count."),
    MetricEventDefinition(
        "code.lines_changed",
        "engineering",
        "lines",
        "code.lines_added and code.lines_deleted",
        "Total edit volume.",
        "code.lines_added + code.lines_deleted",
    ),
    MetricEventDefinition(
        "benchmark.task_result",
        "benchmark",
        "tasks",
        "benchmark_result events and runs session_benchmark_map",
        "Task-level benchmark results associated with a session.",
        "count(session.benchmarks)",
    ),
    MetricEventDefinition(
        "tool.call",
        "agent_behavior",
        "calls",
        "tool_call events and Codex response_item tool calls",
        "Tool invocation count by tool name.",
        "count(tool_call where labels.tool=tool)",
        ("tool",),
    ),
    MetricEventDefinition(
        "tool.error",
        "agent_behavior",
        "calls",
        "trace tool events and tool outputs",
        "Tool calls whose trace status or output indicates an error.",
        "count(trace.tool where status=error or output contains failure markers)",
    ),
    MetricEventDefinition("plan.update", "planning", "updates", "update_plan tool and trace events", "Plan update count.", "max(tool.update_plan, count(trace.update_plan))"),
    MetricEventDefinition("chaos.tool_entropy", "chaos", "bits", "tool.call distribution", "Shannon entropy of tool usage.", "-sum(p(tool) * log2(p(tool)))"),
    MetricEventDefinition(
        "output.code_density",
        "local_optimum",
        "lines/call",
        "code.lines_changed and tool.call",
        "Changed lines divided by total tool calls.",
        "code.lines_changed / tool_call_count",
    ),
)


SESSION_METRICS: list[MetricDefinition] = [
    _metric(
        "model_size_billions",
        "Model Size",
        "model",
        "Model",
        "B",
        "Parsed or fallback model scale in billions of parameters.",
        _model_size_billions,
        formula="parse(model.parameters.declared_size || model.parameters.size) || fallback(model.name)",
        inputs=["model.name", "model.parameters.declared_size", "model.parameters.size", "agentminmax/data/model_sizes.json"],
        labels=_model_size_metric_labels,
    ),
    _metric(
        "active_model_size_billions",
        "Active Model Size",
        "model",
        "Model",
        "B",
        "Activated parameters per token when known; unknown when no active-size estimate is available.",
        _active_model_size_billions,
        formula="fallback(model.name).active_parameter_billions || unknown",
        inputs=["model.name", "agentminmax/data/model_sizes.json"],
    ),
    _metric(
        "model_absorption",
        "Model Absorption",
        "model",
        "Model",
        "ratio",
        "Estimated share of task complexity absorbed by model scale.",
        _model_absorption,
        formula="piecewise(model.size_billions)",
        inputs=["model.size_billions"],
    ),
    _metric(
        "intrinsic_score",
        "Intrinsic Score",
        "complexity",
        "Complexity",
        "score",
        "Task complexity before model absorption.",
        lambda s: _session_complexity(s).intrinsic_score,
        formula="log1p(tokens.total)/2 + 1.35*tool_calls + 0.55*unique_tools + benchmark/task/code/time terms",
        inputs=[
            "token.input",
            "token.output",
            "tool.call",
            "benchmark.task_result",
            "code.lines_changed",
            "duration_seconds",
        ],
        display={"kind": "histogram"},
    ),
    _metric(
        "effective_score",
        "Effective Score",
        "complexity",
        "Complexity",
        "score",
        "Complexity remaining after model absorption.",
        lambda s: _session_complexity(s).effective_score,
        formula="complexity.intrinsic_score * (1 - model.absorption)",
        inputs=["complexity.intrinsic_score", "model.absorption"],
    ),
    _metric(
        "chaos_score",
        "Chaos Score",
        "complexity",
        "Complexity",
        "score",
        "Proxy for failed benchmarks, deletion churn, and quality gap.",
        lambda s: _session_complexity(s).chaos_score,
        formula="failed_benchmarks + 0.01*code.lines_deleted + 0.25*quality_gap",
        inputs=["benchmark.task_result.completed", "code.lines_deleted", "benchmark.task_result.quality_score"],
    ),
    _metric(
        "recommended_grain",
        "Recommended Grain",
        "complexity",
        "Complexity",
        "class",
        "Recommended agent goal grain from effective complexity score.",
        lambda s: _session_complexity(s).recommended_grain,
        formula="bucket(complexity.effective_score)",
        inputs=["complexity.effective_score"],
    ),
    _metric(
        "intent_kind",
        "Intent Kind",
        "intent",
        "Intent And Grain",
        "class",
        "Heuristic task intent from prompt and artifacts.",
        _intent_kind,
        formula="heuristic(logs, code.lines_changed, benchmark.task_result)",
        inputs=["message.content", "code.lines_changed", "benchmark.task_result"],
    ),
    _metric(
        "expected_artifact",
        "Expected Artifact",
        "intent",
        "Intent And Grain",
        "class",
        "Likely output artifact type.",
        _expected_artifact,
        formula="heuristic(intent_kind, code.lines_changed, benchmark.task_result)",
        inputs=["metric.intent_kind", "code.lines_changed", "benchmark.task_result"],
    ),
    _metric(
        "model_normalized_grain",
        "Model-Normalized Grain",
        "intent",
        "Intent And Grain",
        "score",
        "Complexity remaining after model absorption.",
        _model_normalized_grain,
        formula="complexity.effective_score",
        inputs=["complexity.effective_score", "model.parameters.declared_size"],
    ),
    _metric(
        "context_utilization",
        "Context Utilization",
        "llm",
        "LLM Runtime",
        "ratio",
        "Input tokens divided by declared context window.",
        _context_utilization,
        formula="token.input / model.context_window",
        inputs=["token.input", "model.context_window"],
    ),
    _metric(
        "input_output_expansion_ratio",
        "Input/Output Expansion",
        "llm",
        "LLM Runtime",
        "ratio",
        "Output tokens divided by input tokens.",
        _input_output_expansion_ratio,
        formula="token.output / token.input",
        inputs=["token.output", "token.input"],
    ),
    _metric(
        "cache_hit_ratio",
        "Cache Hit Ratio",
        "llm",
        "LLM Runtime",
        "ratio",
        "Cached input tokens divided by input tokens.",
        _cache_hit_ratio,
        formula="token.cached_input / token.input",
        inputs=["token.cached_input", "token.input"],
    ),
    _metric(
        "tokens_per_second",
        "Tokens Per Second",
        "llm",
        "LLM Runtime",
        "tokens/s",
        "Total tokens divided by wall-clock duration.",
        _tokens_per_second,
        formula="(token.input + token.output) / duration_seconds",
        inputs=["token.input", "token.output", "duration_seconds"],
    ),
    _metric(
        "tool_call_count",
        "Tool Calls",
        "agent_behavior",
        "Tools And Calls",
        "calls",
        "Total tool calls.",
        lambda s: sum(s.tool_calls.values()),
        formula="sum(tool.call)",
        inputs=["tool.call"],
        display={"kind": "bars"},
    ),
    _metric(
        "unique_tool_count",
        "Unique Tools",
        "agent_behavior",
        "Tools And Calls",
        "tools",
        "Distinct tool names used.",
        lambda s: len(s.tool_calls),
        formula="count(distinct tool.call.tool)",
        inputs=["tool.call"],
    ),
    _metric(
        "tool_error_count",
        "Tool Errors",
        "agent_behavior",
        "Tools And Calls",
        "calls",
        "Tool trace events with error status.",
        _tool_error_count,
        formula="count(trace.tool where status=error)",
        inputs=["trace.tool.status", "trace.tool.summary", "trace.tool.output"],
    ),
    _metric(
        "tool_success_rate",
        "Tool Success Rate",
        "agent_behavior",
        "Tools And Calls",
        "ratio",
        "Tool calls not associated with observed error traces.",
        _tool_success_rate,
        formula="(tool_call_count - tool_error_count) / tool_call_count",
        inputs=["metric.tool_call_count", "metric.tool_error_count"],
    ),
    _metric(
        "retry_ratio",
        "Retry Ratio",
        "agent_behavior",
        "Tools And Calls",
        "ratio",
        "Repeated tool calls divided by total tool calls.",
        _retry_ratio,
        formula="sum(max(tool_count - 1, 0)) / tool_call_count",
        inputs=["tool.call"],
    ),
    _metric(
        "patch_failure_count",
        "Patch Failures",
        "agent_behavior",
        "Tools And Calls",
        "failures",
        "Observed patch verification or patch_apply_end failures.",
        _patch_failure_count,
        formula="count(patch trace failures)",
        inputs=["trace.patch.status", "trace.patch.summary", "trace.patch.output"],
    ),
    _metric(
        "plan_update_count",
        "Plan Updates",
        "planning",
        "Planning",
        "updates",
        "Observed update_plan events from tools and traces.",
        _plan_update_count,
        formula="max(tool.update_plan, count(trace.update_plan))",
        inputs=["tool.update_plan", "trace.update_plan"],
    ),
    _metric(
        "plan_churn_proxy",
        "Plan Churn Proxy",
        "planning",
        "Planning",
        "ratio",
        "Plan update count divided by maximum observed plan width.",
        _plan_churn_proxy,
        formula="plan_update_count / max(len(trace.update_plan.plan))",
        inputs=["metric.plan_update_count", "trace.update_plan.args.plan"],
    ),
    _metric(
        "dag_width_proxy",
        "DAG Width Proxy",
        "dag",
        "DAG And Plan Shape",
        "items",
        "Maximum observed plan item count as a DAG width proxy.",
        _plan_width_proxy,
        formula="max(len(trace.update_plan.plan))",
        inputs=["trace.update_plan.args.plan"],
    ),
    _metric(
        "leaf_pending_ratio",
        "Leaf Pending Ratio",
        "dag",
        "DAG And Plan Shape",
        "ratio",
        "Pending plan leaves divided by maximum observed plan width.",
        _leaf_pending_ratio,
        formula="pending(latest_plan) / dag_width_proxy",
        inputs=["trace.update_plan.args.plan", "metric.dag_width_proxy"],
    ),
    _metric(
        "tool_entropy",
        "Tool Entropy",
        "chaos",
        "Chaos Signals",
        "bits",
        "Shannon entropy of tool-call distribution.",
        _tool_entropy,
        formula="-sum(p(tool) * log2(p(tool)))",
        inputs=["tool.call"],
    ),
    _metric(
        "error_pressure",
        "Error Pressure",
        "chaos",
        "Chaos Signals",
        "ratio",
        "Tool errors divided by total tool calls.",
        _error_pressure,
        formula="tool_error_count / tool_call_count",
        inputs=["metric.tool_error_count", "metric.tool_call_count"],
    ),
    _metric(
        "exploration_to_edit_ratio",
        "Exploration/Edit Ratio",
        "local_optimum",
        "Local Optimum Signals",
        "ratio",
        "Read/search tool calls divided by edit tool calls.",
        _exploration_to_edit_ratio,
        formula="read_search_tool_calls / edit_tool_calls",
        inputs=["tool.call"],
    ),
    _metric(
        "effective_output_density",
        "Effective Output Density",
        "local_optimum",
        "Local Optimum Signals",
        "lines/call",
        "Changed lines divided by total tool calls.",
        _effective_output_density,
        formula="code.lines_changed / tool_call_count",
        inputs=["code.lines_changed", "metric.tool_call_count"],
    ),
    _metric(
        "local_optimum_signal",
        "Local Optimum Signal",
        "local_optimum",
        "Local Optimum Signals",
        "score",
        "Composite proxy for low-quality high-exploration local iteration.",
        _local_optimum_signal,
        formula="((1 - benchmark_quality) + min(exploration_edit_ratio / 10, 1) + min(retry_ratio, 1)) / 3",
        inputs=["metric.benchmark_quality", "metric.exploration_to_edit_ratio", "metric.retry_ratio"],
    ),
    _metric(
        "files_changed",
        "Files Changed",
        "engineering",
        "Engineering Output",
        "files",
        "Files changed by structured code metrics.",
        lambda s: s.code.files_changed,
        formula="code.files_changed",
        inputs=["code.files_changed"],
    ),
    _metric(
        "lines_changed",
        "Lines Changed",
        "engineering",
        "Engineering Output",
        "lines",
        "Added plus deleted lines.",
        lambda s: s.code.lines_changed,
        formula="code.lines_added + code.lines_deleted",
        inputs=["code.lines_added", "code.lines_deleted"],
    ),
    _metric(
        "churn_proxy",
        "Churn Proxy",
        "engineering",
        "Engineering Output",
        "ratio",
        "Deleted lines divided by total changed lines.",
        _churn_proxy,
        formula="code.lines_deleted / code.lines_changed",
        inputs=["code.lines_deleted", "code.lines_changed"],
    ),
    _metric(
        "test_pass_rate",
        "Test Pass Rate",
        "engineering",
        "Engineering Output",
        "ratio",
        "Passed benchmark tests divided by total tests.",
        _test_pass_rate,
        formula="sum(benchmark.tests_passed) / sum(benchmark.tests_total)",
        inputs=["benchmark.tests_passed", "benchmark.tests_total"],
    ),
    _metric(
        "benchmark_result_count",
        "Benchmark Results",
        "benchmark",
        "Benchmark Signals",
        "tasks",
        "Task-level benchmark result count.",
        lambda s: len(s.benchmarks),
        formula="count(benchmark.task_result)",
        inputs=["benchmark.task_result"],
    ),
    _metric(
        "benchmark_completion_rate",
        "Benchmark Completion",
        "benchmark",
        "Benchmark Signals",
        "ratio",
        "Completed benchmark tasks divided by result count.",
        _session_benchmark_completion_rate,
        formula="count(completed benchmark.task_result) / count(benchmark.task_result)",
        inputs=["benchmark.task_result.completed"],
    ),
    _metric(
        "benchmark_quality",
        "Benchmark Quality",
        "benchmark",
        "Benchmark Signals",
        "score",
        "Average task quality score.",
        _session_benchmark_quality,
        formula="mean(benchmark.task_result.quality_score)",
        inputs=["benchmark.task_result.quality_score"],
    ),
]


BENCHMARK_METRICS: list[MetricDefinition] = [
    _metric(
        "pass_rate",
        "Pass Rate",
        "benchmark_quality",
        "Benchmark Quality",
        "ratio",
        "Completed tasks divided by total benchmark results.",
        lambda r: r.completion_rate,
        formula="run.completed_count / run.task_count",
        inputs=["run.completed_count", "run.task_count"],
        display={"kind": "bars"},
    ),
    _metric(
        "average_quality_score",
        "Average Quality",
        "benchmark_quality",
        "Benchmark Quality",
        "score",
        "Mean quality score over task results.",
        lambda r: r.average_quality_score,
        formula="mean(benchmark_result.quality_score)",
        inputs=["benchmark_result.quality_score"],
    ),
    _metric(
        "completed_count",
        "Completed Tasks",
        "benchmark_quality",
        "Benchmark Quality",
        "tasks",
        "Completed benchmark tasks.",
        lambda r: r.completed_count,
        formula="sum(benchmark_result.completed)",
        inputs=["benchmark_result.completed"],
    ),
    _metric(
        "task_count",
        "Task Count",
        "benchmark_quality",
        "Benchmark Quality",
        "tasks",
        "Distinct task count.",
        lambda r: r.task_count,
        formula="count(distinct benchmark_result.task_id)",
        inputs=["benchmark_result.task_id"],
    ),
    _metric(
        "tokens_per_task",
        "Tokens Per Task",
        "benchmark_cost",
        "Benchmark Cost",
        "tokens/task",
        "Total tokens divided by task count.",
        _run_tokens_per_task,
        formula="run.total_tokens / run.task_count",
        inputs=["run.total_tokens", "run.task_count"],
        display={"kind": "bars"},
    ),
    _metric(
        "tool_calls_per_task",
        "Tool Calls Per Task",
        "benchmark_cost",
        "Benchmark Cost",
        "calls/task",
        "Tool calls divided by task count.",
        _run_tool_calls_per_task,
        formula="run.total_tool_calls / run.task_count",
        inputs=["run.total_tool_calls", "run.task_count"],
    ),
    _metric(
        "duration_per_task",
        "Duration Per Task",
        "benchmark_cost",
        "Benchmark Cost",
        "seconds/task",
        "Wall-clock seconds divided by task count.",
        _run_duration_per_task,
        formula="run.total_duration_seconds / run.task_count",
        inputs=["run.total_duration_seconds", "run.task_count"],
    ),
    _metric(
        "lines_changed_per_task",
        "Lines Changed Per Task",
        "benchmark_cost",
        "Benchmark Cost",
        "lines/task",
        "Changed lines divided by task count.",
        _run_lines_changed_per_task,
        formula="run.total_lines_changed / run.task_count",
        inputs=["run.total_lines_changed", "run.task_count"],
    ),
    _metric(
        "cost_per_pass",
        "Tokens Per Completed Task",
        "benchmark_cost",
        "Benchmark Cost",
        "tokens/pass",
        "Total tokens divided by completed tasks.",
        _run_cost_per_pass,
        formula="run.total_tokens / run.completed_count",
        inputs=["run.total_tokens", "run.completed_count"],
    ),
    _metric(
        "sessions_per_task",
        "Sessions Per Task",
        "benchmark_cost",
        "Benchmark Cost",
        "sessions/task",
        "Contributing sessions divided by task count.",
        _run_sessions_per_task,
        formula="run.session_count / run.task_count",
        inputs=["run.session_count", "run.task_count"],
    ),
    _metric(
        "completion_variance_proxy",
        "Completion Variance Proxy",
        "benchmark_stability",
        "Benchmark Stability",
        "variance",
        "Bernoulli variance proxy from benchmark completion rate.",
        _run_completion_variance_proxy,
        formula="pass_rate * (1 - pass_rate)",
        inputs=["metric.pass_rate"],
    ),
    _metric(
        "average_tokens_per_session",
        "Average Tokens Per Session",
        "benchmark_stability",
        "Benchmark Stability",
        "tokens/session",
        "Total tokens divided by contributing sessions.",
        _run_average_tokens_per_session,
        formula="run.total_tokens / run.session_count",
        inputs=["run.total_tokens", "run.session_count"],
    ),
    _metric(
        "depth_cost_proxy",
        "Depth Cost Proxy",
        "benchmark_stability",
        "Benchmark Stability",
        "calls/session",
        "Tool calls divided by contributing sessions.",
        _run_depth_cost_proxy,
        formula="run.total_tool_calls / run.session_count",
        inputs=["run.total_tool_calls", "run.session_count"],
    ),
]
