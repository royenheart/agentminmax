from pathlib import Path

from agentminmax.benchmarks import list_benchmarks, load_benchmark_results


FIXTURES = Path(__file__).parent / "fixtures"


def test_list_benchmarks_includes_long_horizon_agent_suites():
    names = {benchmark.name for benchmark in list_benchmarks()}

    assert "swe-bench-verified" in names
    assert "osworld" in names
    assert "webarena" in names
    assert "visualwebarena" in names
    assert "terminal-bench" in names
    assert "the-agent-company" in names
    assert "codeclash" in names


def test_load_benchmark_results_normalizes_external_json():
    results = load_benchmark_results(FIXTURES / "benchmark-results.json")

    assert [result.benchmark for result in results] == ["osworld", "webarena"]
    assert results[0].completed is False
    assert results[0].quality_score == 0.46
    assert results[1].completed is True
    assert results[1].duration_seconds == 420
