from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LiveTask:
    index: int
    benchmark: str
    task_id: str
    instructions: str
    files: dict[str, str]
    tests_total: int
    expected_outputs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def directory_name(self) -> str:
        return f"{self.index:02d}-{self.task_id}"


LIVE_TASKS: tuple[LiveTask, ...] = (
    LiveTask(
        index=1,
        benchmark="HumanEval-lite",
        task_id="humaneval_has_close_elements",
        tests_total=4,
        expected_outputs=("solution.py",),
        instructions=(
            "Implement `has_close_elements(numbers, threshold)` in `solution.py`. "
            "Return True when any two distinct numbers differ by less than threshold."
        ),
        files={
            "README_TASK.md": (
                "# has_close_elements\n\n"
                "Implement `has_close_elements(numbers, threshold)` in `solution.py`.\n"
                "Return True when any two distinct numbers differ by less than `threshold`.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "solution.py": (
                "def has_close_elements(numbers, threshold):\n"
                "    raise NotImplementedError\n"
            ),
            "check.py": (
                "from solution import has_close_elements\n\n"
                "assert has_close_elements([1.0, 2.0, 3.0], 0.5) is False\n"
                "assert has_close_elements([1.0, 2.8, 3.0, 4.0], 0.3) is True\n"
                "assert has_close_elements([], 1.0) is False\n"
                "assert has_close_elements([5.0, 5.4], 0.5) is True\n"
                "print('ok')\n"
            ),
        },
    ),
    LiveTask(
        index=2,
        benchmark="HumanEval-lite",
        task_id="humaneval_below_zero",
        tests_total=4,
        expected_outputs=("solution.py",),
        instructions=(
            "Implement `below_zero(operations)` in `solution.py`. "
            "The balance starts at zero; return True if any prefix sum is below zero."
        ),
        files={
            "README_TASK.md": (
                "# below_zero\n\n"
                "Implement `below_zero(operations)` in `solution.py`.\n"
                "The balance starts at zero. Return True if any prefix sum becomes negative.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "solution.py": (
                "def below_zero(operations):\n"
                "    raise NotImplementedError\n"
            ),
            "check.py": (
                "from solution import below_zero\n\n"
                "assert below_zero([1, 2, -4, 1]) is True\n"
                "assert below_zero([1, 2, -3, 1]) is False\n"
                "assert below_zero([]) is False\n"
                "assert below_zero([-1]) is True\n"
                "print('ok')\n"
            ),
        },
    ),
    LiveTask(
        index=3,
        benchmark="MBPP-lite",
        task_id="mbpp_largest_divisor",
        tests_total=4,
        expected_outputs=("solution.py",),
        instructions=(
            "Implement `largest_divisor(n)` in `solution.py`. "
            "Return the largest proper divisor of n."
        ),
        files={
            "README_TASK.md": (
                "# largest_divisor\n\n"
                "Implement `largest_divisor(n)` in `solution.py`.\n"
                "Return the largest positive divisor of `n` that is smaller than `n`.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "solution.py": (
                "def largest_divisor(n):\n"
                "    raise NotImplementedError\n"
            ),
            "check.py": (
                "from solution import largest_divisor\n\n"
                "assert largest_divisor(15) == 5\n"
                "assert largest_divisor(49) == 7\n"
                "assert largest_divisor(7) == 1\n"
                "assert largest_divisor(100) == 50\n"
                "print('ok')\n"
            ),
        },
    ),
    LiveTask(
        index=4,
        benchmark="MBPP-lite",
        task_id="mbpp_sort_matrix_by_row_sum",
        tests_total=3,
        expected_outputs=("solution.py",),
        instructions=(
            "Implement `sort_matrix_by_row_sum(matrix)` in `solution.py`. "
            "Return rows sorted by ascending row sum, preserving row contents."
        ),
        files={
            "README_TASK.md": (
                "# sort_matrix_by_row_sum\n\n"
                "Implement `sort_matrix_by_row_sum(matrix)` in `solution.py`.\n"
                "Return a new matrix with rows sorted by ascending row sum.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "solution.py": (
                "def sort_matrix_by_row_sum(matrix):\n"
                "    raise NotImplementedError\n"
            ),
            "check.py": (
                "from solution import sort_matrix_by_row_sum\n\n"
                "assert sort_matrix_by_row_sum([[3, 3], [1, 1], [2, 2]]) == [[1, 1], [2, 2], [3, 3]]\n"
                "assert sort_matrix_by_row_sum([[5], [-1, 1], [2]]) == [[-1, 1], [2], [5]]\n"
                "assert sort_matrix_by_row_sum([]) == []\n"
                "print('ok')\n"
            ),
        },
    ),
    LiveTask(
        index=5,
        benchmark="Terminal-Bench-lite",
        task_id="terminal_top_5xx_ip",
        tests_total=3,
        expected_outputs=("answer.txt",),
        instructions=(
            "Read `access.log` and write `answer.txt` with the IP address that produced the most "
            "5xx responses, followed by the count, as `IP COUNT`."
        ),
        files={
            "README_TASK.md": (
                "# top 5xx IP\n\n"
                "Read `access.log` and write `answer.txt` with the IP address that produced the most 5xx responses.\n"
                "The file must contain exactly one line: `IP COUNT`.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "access.log": (
                "10.0.0.1 200 /index\n"
                "10.0.0.2 500 /checkout\n"
                "10.0.0.3 502 /api\n"
                "10.0.0.2 503 /checkout\n"
                "10.0.0.4 404 /missing\n"
                "10.0.0.2 500 /pay\n"
                "10.0.0.3 200 /api\n"
                "10.0.0.1 501 /index\n"
            ),
            "check.py": (
                "from pathlib import Path\n\n"
                "answer = Path('answer.txt').read_text(encoding='utf-8').strip()\n"
                "assert answer == '10.0.0.2 3'\n"
                "parts = answer.split()\n"
                "assert len(parts) == 2\n"
                "assert parts[1].isdigit()\n"
                "print('ok')\n"
            ),
        },
    ),
    LiveTask(
        index=6,
        benchmark="Terminal-Bench-lite",
        task_id="terminal_orders_report",
        tests_total=3,
        expected_outputs=("report.json",),
        instructions=(
            "Read `orders.csv` and create `report.json` containing region totals and `order_count`."
        ),
        files={
            "README_TASK.md": (
                "# orders report\n\n"
                "Read `orders.csv` and create `report.json`.\n"
                "The JSON must be `{\"regions\":{\"us\":15.0,\"eu\":10.0,\"apac\":10.0},\"order_count\":5}`.\n"
                "Run `python check.py` before finishing.\n"
            ),
            "orders.csv": (
                "id,region,amount\n"
                "1,us,10.0\n"
                "2,eu,7.5\n"
                "3,apac,10.0\n"
                "4,us,5.0\n"
                "5,eu,2.5\n"
            ),
            "check.py": (
                "import json\n"
                "from pathlib import Path\n\n"
                "payload = json.loads(Path('report.json').read_text(encoding='utf-8'))\n"
                "assert payload == {'regions': {'us': 15.0, 'eu': 10.0, 'apac': 10.0}, 'order_count': 5}\n"
                "assert sorted(payload['regions']) == ['apac', 'eu', 'us']\n"
                "assert sum(payload['regions'].values()) == 35.0\n"
                "print('ok')\n"
            ),
        },
    ),
)


def prepare_experiment(
    *,
    runs_root: str | Path = "runs",
    experiment_id: str | None = None,
    task_ids: list[str] | None = None,
    codex_home: str | Path | None = None,
    dry_run: bool = False,
) -> Path:
    experiment = experiment_id or _default_experiment_id()
    run_dir = Path(runs_root).expanduser() / experiment
    run_dir.mkdir(parents=True, exist_ok=True)
    selected = _select_tasks(task_ids)
    codex_home_path = Path(codex_home or os.environ.get("CODEX_HOME", "~/.codex")).expanduser()

    entries: list[dict[str, Any]] = []
    for task in selected:
        task_dir = run_dir / "tasks" / task.directory_name
        task_dir.mkdir(parents=True, exist_ok=True)
        for relative_path, content in task.files.items():
            target = task_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        entries.append(_map_entry(task, run_dir=run_dir, task_dir=task_dir, session_id=None))

    _write_json(run_dir / "experiment.json", _experiment_payload(experiment, codex_home_path, selected, dry_run=dry_run))
    _write_json(
        run_dir / "session_benchmark_map.json",
        {
            "schema_version": 1,
            "experiment_id": experiment,
            "codex_home": str(codex_home_path),
            "entries": entries,
        },
    )
    return run_dir


def run_experiment(
    *,
    runs_root: str | Path = "runs",
    experiment_id: str | None = None,
    task_ids: list[str] | None = None,
    codex_home: str | Path | None = None,
    codex_bin: str = "codex",
    model: str | None = None,
    dry_run: bool = False,
) -> Path:
    run_dir = prepare_experiment(
        runs_root=runs_root,
        experiment_id=experiment_id,
        task_ids=task_ids,
        codex_home=codex_home,
        dry_run=dry_run,
    )
    if dry_run:
        (run_dir / "results.jsonl").write_text("", encoding="utf-8")
        return run_dir

    codex_home_path = Path(codex_home or os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    selected = _select_tasks(task_ids)
    entries: list[dict[str, Any]] = []
    result_lines: list[str] = []
    for task in selected:
        task_dir = run_dir / "tasks" / task.directory_name
        before = _session_files(codex_home_path)
        started = datetime.now(tz=timezone.utc)
        codex_result = _run_codex_task(task, task_dir, codex_home_path, codex_bin=codex_bin, model=model)
        session_id = _new_session_id(codex_home_path, before)
        check_result = subprocess.run(
            [sys.executable, "check.py"],
            cwd=task_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        finished = datetime.now(tz=timezone.utc)
        completed = codex_result.returncode == 0 and check_result.returncode == 0
        tests_passed = task.tests_total if completed else 0
        result_lines.append(
            json.dumps(
                {
                    "type": "benchmark_result",
                    "benchmark": task.benchmark,
                    "task_id": task.task_id,
                    "completed": completed,
                    "quality_score": 1.0 if completed else 0.0,
                    "tests_passed": tests_passed,
                    "tests_total": task.tests_total,
                    "duration_seconds": round((finished - started).total_seconds(), 3),
                }
            )
        )
        result_lines.append(json.dumps(_code_metric(task, task_dir)))
        entries.append(_map_entry(task, run_dir=run_dir, task_dir=task_dir, session_id=session_id))
        (task_dir / "check.stdout").write_text(check_result.stdout, encoding="utf-8")
        (task_dir / "check.stderr").write_text(check_result.stderr, encoding="utf-8")

    (run_dir / "results.jsonl").write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    _write_json(
        run_dir / "session_benchmark_map.json",
        {
            "schema_version": 1,
            "experiment_id": run_dir.name,
            "codex_home": str(codex_home_path),
            "entries": entries,
        },
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AgentMinMax live benchmark experiments.")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", "~/.codex"))
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--task", action="append", dest="task_ids", help="Task id to run. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Only write task scaffolds and mapping.")
    parser.add_argument("--list", action="store_true", help="List available live tasks.")
    args = parser.parse_args(argv)

    if args.list:
        for task in LIVE_TASKS:
            print(f"{task.task_id}\t{task.benchmark}")
        return 0

    run_dir = run_experiment(
        runs_root=args.runs_root,
        experiment_id=args.experiment_id,
        task_ids=args.task_ids,
        codex_home=args.codex_home,
        codex_bin=args.codex_bin,
        model=args.model,
        dry_run=args.dry_run,
    )
    print(run_dir)
    return 0


def _run_codex_task(
    task: LiveTask,
    task_dir: Path,
    codex_home: Path,
    *,
    codex_bin: str,
    model: str | None,
) -> subprocess.CompletedProcess[str]:
    prompt = (
        f"{task.instructions}\n\n"
        "Work only in the current task directory. Do not edit check.py. "
        "Before the final response, run `python check.py` and ensure it passes."
    )
    command = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "danger-full-access",
        "--ask-for-approval",
        "never",
        "-C",
        str(task_dir),
        "-o",
        str(task_dir / "codex-last-message.txt"),
        "--json",
        "-",
    ]
    if model:
        command[2:2] = ["--model", model]
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False, env=env)
    (task_dir / "codex-events.jsonl").write_text(result.stdout, encoding="utf-8")
    (task_dir / "codex.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def _select_tasks(task_ids: list[str] | None) -> list[LiveTask]:
    if not task_ids:
        return list(LIVE_TASKS)
    tasks_by_id = {task.task_id: task for task in LIVE_TASKS}
    missing = [task_id for task_id in task_ids if task_id not in tasks_by_id]
    if missing:
        raise ValueError(f"unknown task id(s): {', '.join(missing)}")
    return [tasks_by_id[task_id] for task_id in task_ids]


def _map_entry(task: LiveTask, *, run_dir: Path, task_dir: Path, session_id: str | None) -> dict[str, Any]:
    return {
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "session_id": session_id,
        "run_id": run_dir.name,
        "task_dir": str(task_dir.relative_to(run_dir)),
    }


def _experiment_payload(experiment_id: str, codex_home: Path, tasks: list[LiveTask], *, dry_run: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": "codex",
        "codex_home": str(codex_home),
        "dry_run": dry_run,
        "tasks": [{"benchmark": task.benchmark, "task_id": task.task_id} for task in tasks],
    }


def _default_experiment_id() -> str:
    return "codex-live-" + datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")


def _session_files(codex_home: Path) -> set[Path]:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return set()
    return set(sessions_root.rglob("*.jsonl"))


def _new_session_id(codex_home: Path, before: set[Path]) -> str | None:
    new_files = sorted(_session_files(codex_home) - before, key=lambda path: path.stat().st_mtime, reverse=True)
    for path in new_files:
        session_id = _session_id_from_file(path)
        if session_id:
            return session_id
    return None


def _session_id_from_file(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "session_meta":
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if payload.get("id"):
                return str(payload["id"])
        if event.get("type") == "session_start" and event.get("session_id"):
            return str(event["session_id"])
    return None


def _code_metric(task: LiveTask, task_dir: Path) -> dict[str, Any]:
    files_changed = 0
    lines_added = 0
    for relative_path in task.expected_outputs:
        path = task_dir / relative_path
        if not path.exists():
            continue
        files_changed += 1
        lines_added += len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return {
        "type": "code_metric",
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_deleted": 0,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
