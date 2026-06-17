import json
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentminmax", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_summarize_outputs_key_agent_metrics():
    result = run_cli("summarize", str(FIXTURES / "codex-session.jsonl"))

    assert result.returncode == 0, result.stderr
    assert "sessions: 1" in result.stdout
    assert "tokens: 2000" in result.stdout
    assert "tool calls: 2" in result.stdout


def test_cli_demo_writes_dashboard_bundle(tmp_path):
    result = run_cli("demo", "--out", str(tmp_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "observations.json").read_text())
    assert payload["summary"]["session_count"] >= 2
    assert payload["summary"]["total_tool_calls"] > 0


def test_cli_collect_attaches_external_benchmark_results(tmp_path):
    result = run_cli(
        "collect",
        str(FIXTURES / "codex-session.jsonl"),
        "--benchmark-results",
        str(FIXTURES / "benchmark-results.json"),
        "--out",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "observations.json").read_text())
    assert payload["summary"]["session_count"] == 1
    assert len(payload["sessions"][0]["benchmarks"]) == 3
    assert payload["summary"]["benchmark_completion_rate"] == pytest.approx(2 / 3, abs=0.0001)


def test_cli_collect_populates_static_source_metadata(tmp_path):
    trace = tmp_path / "local-run.jsonl"
    trace.write_text(
        '{"type":"session_start","session_id":"s","timestamp":"2026-06-17T00:00:00Z"}\n',
        encoding="utf-8",
    )

    result = run_cli("collect", str(trace), "--out", str(tmp_path / "bundle"))

    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "bundle" / "observations.json").read_text())
    assert payload["sources"][0]["id"] == "local-run"
    assert payload["sources"][0]["path"] == str(trace)
    assert payload["sessions"][0]["source_id"] == "local-run"


def test_cli_run_benchmark_reports_configured_command_failure(tmp_path):
    config_path = tmp_path / "agentminmax.toml"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "port = 9999",
                "",
                "[[sources]]",
                'id = "fail"',
                'label = "Fail"',
                'kind = "command"',
                'command = ["python3", "-c", "import sys; sys.exit(5)"]',
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli("run-benchmark", "fail", "--config", str(config_path), "--bundle", str(tmp_path / "bundle"))

    assert result.returncode == 1
    assert "failed" in result.stdout
    assert "returncode: 5" in result.stdout
