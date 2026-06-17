import json
from pathlib import Path

from agentminmax.config import BenchmarkSource
from agentminmax.ingest import build_observation
from agentminmax.runs import load_run_events
from agentminmax.sources import load_source_events


def test_load_run_events_maps_benchmark_results_to_existing_sessions(tmp_path):
    run_dir = tmp_path / "runs" / "exp-1"
    run_dir.mkdir(parents=True)
    (run_dir / "session_benchmark_map.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "experiment_id": "exp-1",
                "entries": [
                    {
                        "benchmark": "HumanEval-lite",
                        "task_id": "humaneval_has_close_elements",
                        "session_id": "session-1",
                        "run_id": "exp-1",
                        "task_dir": "tasks/01-humaneval_has_close_elements",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "type": "benchmark_result",
                "benchmark": "HumanEval-lite",
                "task_id": "humaneval_has_close_elements",
                "completed": True,
                "quality_score": 1.0,
                "tests_passed": 3,
                "tests_total": 3,
                "duration_seconds": 12.5,
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "code_metric",
                "task_id": "humaneval_has_close_elements",
                "files_changed": 1,
                "lines_added": 4,
                "lines_deleted": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = [
        {
            "type": "session_start",
            "session_id": "session-1",
            "timestamp": "2026-06-17T00:00:00Z",
            "source_id": "codex-home",
            "run_id": "exp-1",
        },
        *load_run_events(tmp_path / "runs", source_id="benchmark-runs"),
    ]
    observation = build_observation(events)

    assert observation.sessions[0].benchmarks[0].benchmark == "HumanEval-lite"
    assert observation.sessions[0].benchmarks[0].task_id == "humaneval_has_close_elements"
    assert observation.sessions[0].code.files_changed == 1
    assert observation.benchmark_runs[0].session_count == 1


def test_source_kinds_load_codex_home_sessions_and_runs(tmp_path):
    codex_home = tmp_path / "codex-home"
    session_dir = codex_home / "sessions" / "2026" / "06" / "17"
    session_dir.mkdir(parents=True)
    (session_dir / "session.jsonl").write_text(
        '{"type":"session_start","session_id":"codex-session","timestamp":"2026-06-17T00:00:00Z"}\n',
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "exp-1"
    run_dir.mkdir(parents=True)
    (run_dir / "session_benchmark_map.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "experiment_id": "exp-1",
                "entries": [
                    {
                        "benchmark": "MBPP-lite",
                        "task_id": "mbpp_largest_divisor",
                        "session_id": "codex-session",
                        "run_id": "exp-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        '{"type":"benchmark_result","benchmark":"MBPP-lite","task_id":"mbpp_largest_divisor","completed":true}\n',
        encoding="utf-8",
    )

    session_events = load_source_events(
        BenchmarkSource(id="codex-home", label="Codex Home", kind="codex_home", path=str(codex_home))
    )
    run_events = load_source_events(
        BenchmarkSource(id="benchmark-runs", label="Benchmark Runs", kind="runs", path=str(tmp_path / "runs"))
    )
    observation = build_observation([*session_events, *run_events])

    assert observation.sessions[0].session_id == "codex-session"
    assert observation.sessions[0].benchmarks[0].benchmark == "MBPP-lite"


def test_session_start_with_null_run_id_does_not_overwrite_benchmark_map_run_id():
    observation = build_observation(
        [
            {
                "type": "benchmark_result",
                "session_id": "session-1",
                "run_id": "exp-1",
                "benchmark": "HumanEval-lite",
                "task_id": "task-1",
                "completed": True,
            },
            {
                "type": "session_start",
                "session_id": "session-1",
                "source_id": "local-codex",
                "run_id": None,
                "timestamp": "2026-06-17T00:00:00Z",
            },
        ]
    )

    assert observation.sessions[0].run_id == "exp-1"
    assert observation.benchmark_runs[0].run_id == "exp-1"
