from __future__ import annotations

import gzip
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from agentminmax.config import AgentMinMaxConfig, BenchmarkSource, load_config, save_config, source_from_dict
from agentminmax.dashboard import GzipStaticHandler, export_dashboard_bundle
from agentminmax.ingest import build_observation
from agentminmax.models import Observation
from agentminmax.payloads import benchmark_run_detail_payload, observation_payload, session_detail_payload
from agentminmax.sources import load_source_events
from agentminmax.traces import benchmark_sessions


@dataclass(slots=True)
class JobRecord:
    id: str
    source_id: str
    action: str
    status: str
    started_at: float
    finished_at: float | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SourceState:
    status: str = "never"
    error: str | None = None
    refreshed_at: float | None = None


@dataclass(slots=True)
class ObservationServer:
    config_path: str | Path
    bundle_dir: str | Path
    config: AgentMinMaxConfig = field(init=False)
    observation: Observation = field(init=False)
    jobs: list[JobRecord] = field(default_factory=list)
    source_state: dict[str, SourceState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.config_path = Path(self.config_path)
        self.bundle_dir = Path(self.bundle_dir)
        self.config = load_config(self.config_path)
        self.observation = self.refresh_all_sources()

    def refresh_all_sources(self) -> Observation:
        events = []
        for source in self.config.sources:
            try:
                events.extend(load_source_events(source))
                self.source_state[source.id] = SourceState(status="ok", refreshed_at=time.time())
            except Exception as exc:  # Keep the last good observation available.
                self.source_state[source.id] = SourceState(status="error", error=str(exc), refreshed_at=time.time())
        observation = build_observation(events, sources=self._sources_payload())
        self.observation = observation
        export_dashboard_bundle(observation, self.bundle_dir)
        return observation

    def refresh_source(self, source_id: str) -> dict:
        source = self._source_by_id(source_id)
        if source is None:
            return self._error("source_not_found", f"No source exists with id '{source_id}'.", 404)
        try:
            events = load_source_events(source)
            other_events = []
            for other in self.config.sources:
                if other.id != source_id:
                    other_events.extend(load_source_events(other))
            observation = build_observation(other_events + events, sources=self._sources_payload())
            self.observation = observation
            self.source_state[source_id] = SourceState(status="ok", refreshed_at=time.time())
            export_dashboard_bundle(observation, self.bundle_dir)
            return {"source_id": source_id, "status": "ok", "events": len(events)}
        except Exception as exc:
            self.source_state[source_id] = SourceState(status="error", error=str(exc), refreshed_at=time.time())
            return self._error("source_refresh_failed", str(exc), 500)

    def run_source(self, source_id: str) -> dict:
        source = self._source_by_id(source_id)
        if source is None:
            return self._error("source_not_found", f"No source exists with id '{source_id}'.", 404)
        if source.kind != "command" or not source.command:
            return self._error("not_command_source", f"Source '{source_id}' is not a command source.", 400)

        job = JobRecord(
            id=f"job-{len(self.jobs) + 1}",
            source_id=source_id,
            action="run",
            status="running",
            started_at=time.time(),
        )
        self.jobs.append(job)
        result = subprocess.run(source.command, text=True, capture_output=True, check=False)
        job.returncode = result.returncode
        job.stdout = result.stdout
        job.stderr = result.stderr
        job.finished_at = time.time()
        job.status = "completed" if result.returncode == 0 else "failed"
        if job.status == "completed":
            self.refresh_source(source_id)
        return job.to_dict()

    def handle_api(self, method: str, path: str, body: bytes) -> tuple[int, dict]:
        parsed = urlparse(path)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        try:
            if method == "GET" and parsed.path == "/api/observation":
                return 200, observation_payload(self.observation)
            if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "sessions"]:
                session = next((item for item in self.observation.sessions if item.session_id == parts[2]), None)
                if session is None:
                    return 404, self._error("session_not_found", f"No session exists with id '{parts[2]}'.", 404)
                return 200, session_detail_payload(session)
            if method == "GET" and len(parts) == 5 and parts[:2] == ["api", "benchmarks"]:
                run = next(
                    (
                        item
                        for item in self.observation.benchmark_runs
                        if item.source_id == parts[2] and item.benchmark == parts[3] and item.run_id == parts[4]
                    ),
                    None,
                )
                if run is None:
                    return 404, self._error("benchmark_not_found", "No benchmark run matches the requested key.", 404)
                return 200, benchmark_run_detail_payload(run, benchmark_sessions(self.observation.sessions, run))
            if method == "GET" and parsed.path == "/api/sources":
                return 200, {"sources": self._sources_payload()}
            if method == "POST" and parsed.path == "/api/sources":
                return 200, self._update_sources(body)
            if method == "GET" and parsed.path == "/api/jobs":
                return 200, {"jobs": [job.to_dict() for job in self.jobs]}
            if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                job = next((item for item in self.jobs if item.id == parts[2]), None)
                if job is None:
                    return 404, self._error("job_not_found", f"No job exists with id '{parts[2]}'.", 404)
                return 200, job.to_dict()
            if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "sources"]:
                if parts[3] == "refresh":
                    payload = self.refresh_source(parts[2])
                    return int(payload.pop("_status", 200)), payload
                if parts[3] == "run":
                    payload = self.run_source(parts[2])
                    return int(payload.pop("_status", 200)), payload
            return 404, self._error("not_found", f"No route for {method} {parsed.path}.", 404)
        except json.JSONDecodeError as exc:
            return 400, self._error("invalid_json", str(exc), 400)

    def _update_sources(self, body: bytes) -> dict:
        payload = json.loads(body.decode("utf-8") or "{}")
        sources_payload = payload.get("sources", [])
        if not isinstance(sources_payload, list):
            return self._error("invalid_sources", "sources must be a list", 400)
        self.config.sources = [source_from_dict(item) for item in sources_payload]
        save_config(self.config, self.config_path)
        self.refresh_all_sources()
        return {"sources": self._sources_payload()}

    def _sources_payload(self) -> list[dict]:
        payload = []
        for source in self.config.sources:
            item = source.to_dict()
            state = self.source_state.get(source.id, SourceState())
            item["last_status"] = state.status
            item["last_error"] = state.error
            item["refreshed_at"] = state.refreshed_at
            payload.append(item)
        return payload

    def _source_by_id(self, source_id: str) -> BenchmarkSource | None:
        return next((source for source in self.config.sources if source.id == source_id), None)

    def _error(self, code: str, message: str, status: int) -> dict:
        return {"_status": status, "error": {"code": code, "message": message}}


def serve_dynamic(config_path: str | Path, bundle_dir: str | Path, host: str, port: int) -> None:
    app = ObservationServer(config_path=config_path, bundle_dir=bundle_dir)

    class Handler(GzipStaticHandler):
        def _handle_api(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            status, payload = app.handle_api(self.command, self.path, body)
            encoded, headers = encode_json_response(payload, self.headers.get("Accept-Encoding", ""))
            self.send_response(status)
            for header, value in headers.items():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/"):
                self._handle_api()
            else:
                super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if self.path.startswith("/api/"):
                self._handle_api()
            else:
                self.send_error(404)

    handler = partial(Handler, directory=str(Path(bundle_dir).resolve()))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentMinMax dynamic dashboard serving at http://{host}:{port}/")
    server.serve_forever()


def encode_json_response(payload: dict, accept_encoding: str = "") -> tuple[bytes, dict[str, str]]:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Vary": "Accept-Encoding",
    }
    if "gzip" in {item.strip().split(";", 1)[0] for item in accept_encoding.lower().split(",")} and len(encoded) > 1024:
        encoded = gzip.compress(encoded, compresslevel=3)
        headers["Content-Encoding"] = "gzip"
    headers["Content-Length"] = str(len(encoded))
    return encoded, headers
