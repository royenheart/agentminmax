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
