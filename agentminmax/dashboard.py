from __future__ import annotations

import gzip
import json
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from agentminmax.models import Observation
from agentminmax.payloads import observation_payload, write_detail_payloads
from agentminmax.traces import export_observation_traces


FRONTEND_ASSET_DIR = Path(__file__).parent / "assets" / "dashboard"
DASHBOARD_ASSETS = {
    "pages/index.html": "index.html",
    "pages/trace.html": "trace.html",
    "styles/styles.css": "styles.css",
    "scripts/app.js": "app.js",
    "scripts/perfetto-embed.js": "perfetto-embed.js",
}
VENDOR_ASSET_DIR = Path(__file__).parent / "assets" / "vendor"
VENDOR_FILES = ("echarts.min.js", "tabulator.min.js", "tabulator.min.css")


def export_dashboard_bundle(observation: Observation, out_dir: str | Path) -> Path:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    export_observation_traces(observation, target)
    stale_trace_js = target / "trace.js"
    if stale_trace_js.exists():
        stale_trace_js.unlink()
    write_detail_payloads(observation, target)
    (target / "observations.json").write_text(
        json.dumps(observation_payload(observation), separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    for source_name, output_name in DASHBOARD_ASSETS.items():
        shutil.copyfile(FRONTEND_ASSET_DIR / source_name, target / output_name)
    vendor_target = target / "vendor"
    vendor_target.mkdir(exist_ok=True)
    for filename in VENDOR_FILES:
        shutil.copyfile(VENDOR_ASSET_DIR / filename, vendor_target / filename)
    write_gzip_json_assets(target)
    return target


def serve_dashboard(bundle_dir: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = partial(GzipStaticHandler, directory=str(Path(bundle_dir).resolve()))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentMinMax dashboard serving at http://{host}:{port}/")
    server.serve_forever()


class GzipStaticHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self._serve_gzip_static_file():
            return
        super().do_GET()

    def _serve_gzip_static_file(self) -> bool:
        accepted = {item.strip().split(";", 1)[0] for item in self.headers.get("Accept-Encoding", "").lower().split(",")}
        if "gzip" not in accepted:
            return False
        parsed = urlparse(self.path)
        requested = Path(self.translate_path(parsed.path))
        if requested.is_dir():
            return False
        gz_path = Path(f"{requested}.gz")
        if not gz_path.exists():
            return False
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(requested)))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(gz_path.stat().st_size))
        self.end_headers()
        with gz_path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)
        return True


def write_gzip_json_assets(target: Path) -> None:
    for path in target.rglob("*.json"):
        path.with_suffix(f"{path.suffix}.gz").write_bytes(gzip.compress(path.read_bytes(), compresslevel=3))
