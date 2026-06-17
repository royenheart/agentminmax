import json
from pathlib import Path

from agentminmax.dashboard import export_dashboard_bundle
from agentminmax.ingest import build_observation, load_jsonl_events


FIXTURES = Path(__file__).parent / "fixtures"


def test_export_dashboard_bundle_writes_static_panel_and_observation_data(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "app.js").exists()

    payload = json.loads((tmp_path / "observations.json").read_text())
    assert payload["summary"]["session_count"] == 1
    assert payload["sessions"][0]["model"]["parameters"]["declared_size"] == "1T"
    assert "complexity" in payload["sessions"][0]


def test_dashboard_bundle_includes_interactive_vendor_assets(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    assert (tmp_path / "vendor" / "echarts.min.js").exists()
    assert (tmp_path / "vendor" / "tabulator.min.js").exists()
    assert (tmp_path / "vendor" / "tabulator.min.css").exists()

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    app = (tmp_path / "app.js").read_text(encoding="utf-8")
    assert "vendor/echarts.min.js" in html
    assert "vendor/tabulator.min.js" in html
    assert "vendor/tabulator.min.css" in html
    assert "echarts.init" in app
    assert "new Tabulator" in app
    assert "/api/sources" in app


def test_dashboard_bundle_exports_trace_files_and_embedded_perfetto_host(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-native-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    trace_file = tmp_path / "traces" / "sessions" / "native-1.json"
    assert trace_file.exists()
    trace_payload = json.loads(trace_file.read_text(encoding="utf-8"))
    event_names = [event["name"] for event in trace_payload["traceEvents"]]
    assert "exec_command" in event_names
    assert "Token usage" in event_names

    observation_payload = json.loads((tmp_path / "observations.json").read_text(encoding="utf-8"))
    session = observation_payload["sessions"][0]
    assert session["trace"]["event_count"] >= 6
    assert session["trace"]["preview_events"]
    assert session["trace"]["perfetto_json"] == "traces/sessions/native-1.json"

    assert (tmp_path / "trace.html").exists()
    assert not (tmp_path / "trace.js").exists()
    assert (tmp_path / "perfetto-embed.js").exists()
    trace_html = (tmp_path / "trace.html").read_text(encoding="utf-8")
    perfetto_js = (tmp_path / "perfetto-embed.js").read_text(encoding="utf-8")
    assert "Perfetto Trace" in trace_html
    assert 'id="perfetto-frame"' in trace_html
    assert "https://ui.perfetto.dev/#!/?mode=embedded" in trace_html
    assert "perfetto-embed.js" in trace_html
    assert "postMessage('PING'" in perfetto_js
    assert "evt.data === 'PONG'" in perfetto_js
    assert "perfetto: {" in perfetto_js
    assert "buffer" in perfetto_js
    assert "title" in perfetto_js
    assert "renderWaterfall" not in perfetto_js
    assert "trace-slice" not in trace_html


def test_dashboard_analysis_panels_embed_perfetto_and_link_to_full_perfetto(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-native-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    app = (tmp_path / "app.js").read_text(encoding="utf-8")

    assert "<h3>Trace Preview</h3>" in html
    assert "session-perfetto-frame" in html
    assert "session-trace-links" in html
    assert "benchmark-perfetto-frame" in html
    assert "benchmark-trace-links" in html
    assert "AgentMinMaxPerfetto.render" in app
    assert "renderTraceLinks" in app
    assert "trace.html?file=" in app
    assert "Open Embedded Perfetto" in app
    assert "Download Perfetto JSON" in app
    assert "renderTracePreview" not in app
    assert "traceTime(" not in app


def test_dashboard_session_analysis_restores_token_growth_chart(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-native-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    app = (tmp_path / "app.js").read_text(encoding="utf-8")

    assert "<h3>Token Growth</h3>" in html
    assert 'id="session-token-growth-chart"' in html
    assert "renderSessionTokenGrowthChart(session)" in app
    assert "tokenGrowthPoints(session)" in app
    assert "session.trace_events || []" in app
    assert 'category === "tokens"' in app
    assert 'name: "Input"' in app
    assert 'name: "Output"' in app
    assert 'name: "Cached Input"' in app


def test_dashboard_places_trace_preview_directly_above_logs(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-native-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    related_index = html.index("<h3>Related Benchmarks</h3>")
    trace_index = html.index("<h3>Trace Preview</h3>")
    logs_index = html.index("<h3>Logs</h3>")
    assert related_index < trace_index < logs_index


def test_dashboard_information_architecture_distinguishes_sessions_from_benchmarks(tmp_path):
    observation = build_observation(load_jsonl_events(FIXTURES / "codex-session.jsonl"))

    export_dashboard_bundle(observation, tmp_path)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    app = (tmp_path / "app.js").read_text(encoding="utf-8")

    source_index = html.index("<h2>Sources</h2>")
    session_index = html.index("<h2>Sessions</h2>")
    session_analysis_index = html.index("<h2>Session Analysis</h2>")
    benchmark_source_index = html.index("<h2>Benchmark Sources</h2>")
    benchmark_index = html.index("<h2>Benchmarks</h2>")
    benchmark_analysis_index = html.index("<h2>Benchmark Analysis</h2>")
    assert source_index < session_index < session_analysis_index < benchmark_source_index < benchmark_index < benchmark_analysis_index
    assert "Benchmark Catalog" not in html
    assert "<h2>Complexity By Session</h2>" not in html
    assert "<h2>Tokens And Tools</h2>" not in html
    assert "<h2>Quality By Benchmark</h2>" not in html
    assert "<h3>Related Benchmarks</h3>" in html
    assert "session-related-benchmarks" in html
    assert "session-benchmark-results" not in html

    assert "renderSourceList" in app
    assert "renderBenchmarkSources" in app
    assert "renderBenchmarkTable" in app
    assert "selectSession" in app
    assert "renderSessionAnalysis" in app
    assert "selectBenchmarkRun" in app
    assert "renderBenchmarkAnalysis" in app
    assert 'sessionTable.on("rowClick", selectSession)' in app
    assert 'benchmarkTable.on("rowClick", selectBenchmarkRun)' in app
    assert "ensureRowDetail" not in app
    assert "toggleRowDetail" not in app
    assert "sessionDetailHtml" not in app
    assert "benchmarkDetailHtml" not in app
    assert "relatedBenchmarkList" in app
    assert 'getElementById("session-related-benchmarks")' in app
    assert 'getElementById("session-benchmark-results")' not in app
    assert "benchmarkResultList(session.benchmarks" not in app
    assert "benchmark_catalog" not in app
