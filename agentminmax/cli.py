from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from agentminmax.benchmarks import load_benchmark_results
from agentminmax.config import load_config
from agentminmax.dashboard import export_dashboard_bundle, serve_dashboard
from agentminmax.demo import demo_observation
from agentminmax.ingest import build_observation, load_many_jsonl, summarize_sessions
from agentminmax.server import ObservationServer, serve_dynamic


COMMON_CODEX_LOG_DIRS = (
    "~/.codex/sessions",
    "~/.codex/logs",
    "~/.agents/sessions",
    ".codex/sessions",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentminmax", description="AgentMinMax observability CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize = subparsers.add_parser("summarize", help="Summarize JSONL trace files")
    summarize.add_argument("inputs", nargs="+", help="JSONL trace files")

    collect = subparsers.add_parser("collect", help="Export a dashboard bundle from JSONL traces")
    collect.add_argument("inputs", nargs="+", help="JSONL trace files or glob patterns")
    collect.add_argument("--benchmark-results", action="append", default=[], help="External benchmark JSON files")
    collect.add_argument("--out", default="dashboard-dist", help="Dashboard bundle output directory")

    demo = subparsers.add_parser("demo", help="Write a demo dashboard bundle")
    demo.add_argument("--out", default="dashboard-dist", help="Dashboard bundle output directory")

    dashboard = subparsers.add_parser("dashboard", help="Serve an existing dashboard bundle")
    dashboard.add_argument("--bundle", default="dashboard-dist", help="Directory containing index.html")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)

    serve = subparsers.add_parser("serve", help="Serve a dynamic dashboard with local API endpoints")
    serve.add_argument("--config", default="agentminmax.toml")
    serve.add_argument("--bundle", default="dashboard-dist")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    run_benchmark = subparsers.add_parser("run-benchmark", help="Run a configured benchmark source command")
    run_benchmark.add_argument("source_id")
    run_benchmark.add_argument("--config", default="agentminmax.toml")
    run_benchmark.add_argument("--bundle", default="dashboard-dist")

    scan = subparsers.add_parser("scan-codex", help="Discover common local Codex JSONL session paths")
    scan.add_argument("--out", default=None, help="Optional dashboard bundle output directory")

    args = parser.parse_args(argv)
    if args.command == "summarize":
        observation = build_observation(load_many_jsonl(args.inputs))
        print_summary(observation.to_dict())
        return 0
    if args.command == "collect":
        inputs = _expand_inputs(args.inputs)
        observation = build_observation(load_many_jsonl(inputs))
        _attach_external_benchmarks(observation, args.benchmark_results)
        export_dashboard_bundle(observation, args.out)
        print(f"dashboard bundle: {Path(args.out).resolve()}")
        print_summary(observation.to_dict())
        return 0
    if args.command == "demo":
        observation = demo_observation()
        export_dashboard_bundle(observation, args.out)
        print(f"dashboard bundle: {Path(args.out).resolve()}")
        print_summary(observation.to_dict())
        return 0
    if args.command == "dashboard":
        serve_dashboard(args.bundle, args.host, args.port)
        return 0
    if args.command == "serve":
        config = load_config(args.config)
        host = args.host or config.server.host
        port = args.port or config.server.port
        serve_dynamic(args.config, args.bundle, host, port)
        return 0
    if args.command == "run-benchmark":
        app = ObservationServer(config_path=args.config, bundle_dir=args.bundle)
        payload = app.run_source(args.source_id)
        status = payload.get("status", "unknown")
        print(f"status: {status}")
        if payload.get("returncode") is not None:
            print(f"returncode: {payload['returncode']}")
        if payload.get("stderr"):
            print(payload["stderr"], end="" if payload["stderr"].endswith("\n") else "\n")
        return 0 if status == "completed" else 1
    if args.command == "scan-codex":
        paths = discover_codex_session_logs()
        if not paths:
            print("No Codex JSONL session logs found in common locations.")
            return 1
        for path in paths:
            print(path)
        if args.out:
            observation = build_observation(load_many_jsonl(paths))
            export_dashboard_bundle(observation, args.out)
            print(f"dashboard bundle: {Path(args.out).resolve()}")
        return 0
    return 2


def print_summary(payload: dict) -> None:
    summary = payload["summary"]
    print(f"sessions: {summary['session_count']}")
    print(f"tokens: {summary['total_tokens']}")
    print(f"tool calls: {summary['total_tool_calls']}")
    print(f"lines changed: {summary['total_lines_changed']}")
    print(f"benchmark completion: {summary['benchmark_completion_rate']:.0%}")
    print(f"average quality: {summary['average_quality_score']:.0%}")


def discover_codex_session_logs() -> list[str]:
    paths: list[str] = []
    for raw_dir in COMMON_CODEX_LOG_DIRS:
        directory = Path(raw_dir).expanduser()
        if not directory.exists():
            continue
        paths.extend(str(path) for path in directory.rglob("*.jsonl"))
    return sorted(paths)


def _expand_inputs(inputs: list[str]) -> list[str]:
    paths: list[str] = []
    for item in inputs:
        matches = glob.glob(item)
        paths.extend(matches if matches else [item])
    return paths


def _attach_external_benchmarks(observation, benchmark_paths: list[str]) -> None:
    if not benchmark_paths:
        return
    if not observation.sessions:
        return
    session = observation.sessions[-1]
    for benchmark_path in benchmark_paths:
        session.benchmarks.extend(load_benchmark_results(benchmark_path))
    observation.summary = summarize_sessions(observation.sessions)


def write_observation_json(observation, out_path: str | Path) -> None:
    Path(out_path).write_text(json.dumps(observation.to_dict(), indent=2), encoding="utf-8")
