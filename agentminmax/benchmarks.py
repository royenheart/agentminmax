from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentminmax.models import BenchmarkResult


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    name: str
    domain: str
    signal: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


BENCHMARKS: tuple[BenchmarkSuite, ...] = (
    BenchmarkSuite(
        "swe-bench-verified",
        "software engineering",
        "issue resolution with human-validated tests",
        "https://www.swebench.com/",
    ),
    BenchmarkSuite(
        "swe-smith",
        "software engineering",
        "generated repository tasks",
        "https://arxiv.org/abs/2504.21798",
    ),
    BenchmarkSuite(
        "osworld",
        "desktop agents",
        "real computer tasks",
        "https://os-world.github.io/",
    ),
    BenchmarkSuite(
        "webarena",
        "web agents",
        "realistic web environment tasks",
        "https://webarena.dev/",
    ),
    BenchmarkSuite(
        "visualwebarena",
        "multimodal web agents",
        "visual web tasks",
        "https://jykoh.com/vwa",
    ),
    BenchmarkSuite(
        "terminal-bench",
        "terminal agents",
        "shell task completion",
        "https://www.tbench.ai/",
    ),
    BenchmarkSuite(
        "the-agent-company",
        "professional agents",
        "company-like long-horizon work",
        "https://arxiv.org/abs/2412.14161",
    ),
    BenchmarkSuite(
        "codeclash",
        "software engineering",
        "goal-oriented repository evolution",
        "https://codeclash.ai/",
    ),
)


def list_benchmarks() -> list[BenchmarkSuite]:
    return list(BENCHMARKS)


def benchmark_catalog() -> list[dict[str, str]]:
    return [benchmark.to_dict() for benchmark in BENCHMARKS]


def normalize_benchmark_result(payload: dict[str, Any]) -> BenchmarkResult:
    tests_passed = int(payload.get("tests_passed", 0) or 0)
    tests_total = int(payload.get("tests_total", 0) or 0)
    quality_score = payload.get("quality_score")
    if quality_score is None and tests_total:
        quality_score = tests_passed / tests_total
    if quality_score is None:
        quality_score = 1.0 if payload.get("completed") else 0.0

    return BenchmarkResult(
        benchmark=str(payload.get("benchmark", "unknown")),
        task_id=str(payload.get("task_id", payload.get("id", "unknown"))),
        completed=bool(payload.get("completed", False)),
        quality_score=round(float(quality_score), 4),
        tests_passed=tests_passed,
        tests_total=tests_total,
        duration_seconds=float(payload.get("duration_seconds", 0.0) or 0.0),
    )


def load_benchmark_results(path: str | Path) -> list[BenchmarkResult]:
    payload = json.loads(Path(path).read_text())
    if isinstance(payload, dict):
        items = payload.get("results", [])
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("Benchmark result file must contain a list or an object with a results list.")
    return [normalize_benchmark_result(item) for item in items]
