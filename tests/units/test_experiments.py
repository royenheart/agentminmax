import json

from experiments import LIVE_TASKS, prepare_experiment


def test_prepare_experiment_writes_live_task_scaffold_and_session_map(tmp_path):
    run_dir = prepare_experiment(
        runs_root=tmp_path / "runs",
        experiment_id="exp-1",
        task_ids=["humaneval_has_close_elements"],
        codex_home=tmp_path / "codex-home",
        dry_run=True,
    )

    task_dir = run_dir / "tasks" / "01-humaneval_has_close_elements"
    mapping = json.loads((run_dir / "session_benchmark_map.json").read_text(encoding="utf-8"))

    assert [task.task_id for task in LIVE_TASKS][:2] == ["humaneval_has_close_elements", "humaneval_below_zero"]
    assert (task_dir / "README_TASK.md").exists()
    assert (task_dir / "check.py").exists()
    assert mapping["experiment_id"] == "exp-1"
    assert mapping["codex_home"] == str(tmp_path / "codex-home")
    assert mapping["entries"][0]["benchmark"] == "HumanEval-lite"
    assert mapping["entries"][0]["task_id"] == "humaneval_has_close_elements"
    assert mapping["entries"][0]["session_id"] is None
