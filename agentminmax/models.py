from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TokenUsage:
    input: int = 0
    output: int = 0
    cached_input: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output


@dataclass(slots=True)
class ModelInfo:
    name: str = "unknown"
    provider: str = "unknown"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CodeMetrics:
    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted


@dataclass(slots=True)
class MetricEvent:
    name: str
    value: float | int | str
    unit: str = "count"
    category: str = "general"
    timestamp: str | None = None
    labels: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricValue:
    metric_id: str
    label: str
    value: float | int | str
    unit: str = "count"
    description: str = ""
    formula: str = ""
    inputs: list[str] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricGroup:
    group_id: str
    label: str
    display: dict[str, Any] = field(default_factory=dict)
    metrics: list[MetricValue] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkResult:
    benchmark: str
    task_id: str
    completed: bool
    quality_score: float
    tests_passed: int = 0
    tests_total: int = 0
    duration_seconds: float = 0.0


@dataclass(slots=True)
class BenchmarkRun:
    source_id: str
    benchmark: str
    run_id: str
    task_count: int
    session_count: int
    completed_count: int
    completion_rate: float
    average_quality_score: float
    total_tokens: int
    total_tool_calls: int
    total_duration_seconds: int
    total_lines_changed: int
    metric_groups: list[MetricGroup] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ComplexityMetrics:
    intrinsic_score: float
    model_absorption: float
    effective_score: float
    recommended_grain: str
    chaos_score: float


@dataclass(slots=True)
class TraceEvent:
    event_id: str
    category: str
    name: str
    phase: str
    timestamp: str | None = None
    end_timestamp: str | None = None
    duration_ms: int = 0
    lane: str = "agent"
    status: str = "unknown"
    summary: str = ""
    detail: str = ""
    call_id: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    tokens: dict[str, int] = field(default_factory=dict)
    raw_type: str = ""


@dataclass(slots=True)
class AgentSession:
    session_id: str
    agent: str
    model: ModelInfo
    source_id: str = "manual"
    run_id: str = "unassigned"
    start_time: str | None = None
    end_time: str | None = None
    duration_seconds: int = 0
    status: str = "unknown"
    tokens: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: dict[str, int] = field(default_factory=dict)
    benchmarks: list[BenchmarkResult] = field(default_factory=list)
    code: CodeMetrics = field(default_factory=CodeMetrics)
    complexity: ComplexityMetrics | None = None
    logs: list[str] = field(default_factory=list)
    trace_events: list[TraceEvent] = field(default_factory=list)
    metric_events: list[MetricEvent] = field(default_factory=list)
    metric_groups: list[MetricGroup] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ObservationSummary:
    session_count: int
    total_tokens: int
    total_tool_calls: int
    total_lines_changed: int
    benchmark_completion_rate: float
    average_quality_score: float


@dataclass(slots=True)
class Observation:
    summary: ObservationSummary
    sessions: list[AgentSession]
    benchmark_runs: list[BenchmarkRun] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    benchmark_catalog: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
