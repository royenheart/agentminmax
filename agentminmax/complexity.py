from __future__ import annotations

import math
import re

from agentminmax.models import AgentSession, ComplexityMetrics


def estimate_model_absorption(parameters: dict[str, object]) -> float:
    """Estimate how much task complexity the model can absorb by itself."""
    raw_size = str(parameters.get("declared_size") or parameters.get("size") or "").strip()
    billions = _parse_model_size_to_billions(raw_size)
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


def compute_complexity(session: AgentSession) -> ComplexityMetrics:
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
    absorption = estimate_model_absorption(session.model.parameters)
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
