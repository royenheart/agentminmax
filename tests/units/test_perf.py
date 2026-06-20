import json
import subprocess
import sys
from pathlib import Path


def test_perf_runner_appends_history_and_generates_trend_site(tmp_path):
    history = tmp_path / "perf-history.jsonl"
    history.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timestamp": "2026-06-19T00:00:00Z",
                "commit": "old",
                "branch": "master",
                "case_id": "ingest_codex_fixture",
                "duration_ms": 50.0,
                "peak_kib": 100.0,
                "rounds": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "tests/perf/run_perf.py",
            "--history",
            str(history),
            "--output-dir",
            str(tmp_path / "site"),
            "--commit",
            "new",
            "--branch",
            "master",
            "--timestamp",
            "2026-06-20T00:00:00Z",
            "--rounds",
            "1",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
    assert records[0]["commit"] == "old"
    assert {record["case_id"] for record in records} >= {"ingest_codex_fixture", "dashboard_export_fixture"}
    latest = [record for record in records if record["commit"] == "new"]
    assert latest
    assert all(record["duration_ms"] > 0 for record in latest)
    assert all(record["peak_kib"] >= 0 for record in latest)

    summary = json.loads((tmp_path / "site" / "perf-summary.json").read_text(encoding="utf-8"))
    assert summary["commit"] == "new"
    assert summary["branch"] == "master"
    assert summary["history_records"] == len(records)
    assert any(case["case_id"] == "ingest_codex_fixture" for case in summary["cases"])

    svg = (tmp_path / "site" / "perf-trends.svg").read_text(encoding="utf-8")
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "polyline" in svg
    assert "ingest_codex_fixture" in svg
    assert "perf-trends.svg" in html


def test_master_only_perf_workflow_persists_history_and_chart():
    workflow = Path(".github/workflows/perf.yml")

    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "branches: [master]" in content
    assert "tests/perf/run_perf.py" in content
    assert "perf-results" in content
    assert "perf-history.jsonl" in content
    assert "perf-trends.svg" in content
    assert "actions/upload-artifact" in content
    assert "contents: write" in content
    assert "Install local act dependencies" in content
    assert "if: ${{ env.ACT }}" in content
    assert content.count("if: ${{ !env.ACT }}") == 3
