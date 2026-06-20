from pathlib import Path


def test_observability_doxyfile_generates_xml_for_metrics_docs():
    doxyfile = Path("docs/observability/Doxyfile")

    content = doxyfile.read_text(encoding="utf-8")

    assert "GENERATE_XML = YES" in content
    assert "GENERATE_HTML = NO" in content
    assert "PYTHON_DOCSTRING = NO" in content
    assert "agentminmax/metrics.py" in content
    assert "agentminmax/models.py" in content
    assert "agentminmax/ingest.py" in content


def test_observability_doc_generator_creates_doxygen_output_directory(tmp_path, monkeypatch):
    from scripts import generate_observability_docs as generator

    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text("OUTPUT_DIRECTORY = build/doxygen-observability\n", encoding="utf-8")
    calls = []

    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(generator.shutil, "which", lambda name: "/usr/bin/doxygen")
    monkeypatch.setattr(generator.subprocess, "run", lambda command, cwd, check: calls.append((command, cwd, check)))

    generator.run_doxygen(doxyfile)

    assert (tmp_path / "build" / "doxygen-observability").is_dir()
    assert calls == [(["/usr/bin/doxygen", str(doxyfile)], tmp_path, True)]


def test_observability_markdown_is_generated_from_metric_definitions():
    from scripts.generate_observability_docs import build_markdown

    markdown = build_markdown(doxygen_summary="Doxygen XML parsed 3 documented files.")

    assert "# AgentMinMax Events And Metrics" in markdown
    assert "Generated from Doxygen XML plus the live metric definitions" in markdown
    assert "Doxygen XML parsed 3 documented files." in markdown
    assert "## Atomic Events" in markdown
    assert "`model.size_billions`" in markdown
    assert "`tool.call`" in markdown
    assert "## Session Metric Groups" in markdown
    assert "### Model" in markdown
    assert "`model_size_billions`" in markdown
    assert "agentminmax/data/model_sizes.json" in markdown
    assert "### Complexity" in markdown
    assert "`effective_score`" in markdown
    assert "`complexity.intrinsic_score * (1 - model.absorption)`" in markdown
    assert "### LLM Runtime" in markdown
    assert "`input_output_expansion_ratio`" in markdown
    assert "`token.output / token.input`" in markdown
    assert "## Benchmark Metric Groups" in markdown
    assert "`tokens_per_task`" in markdown


def test_observability_doc_generator_requires_doxygen_without_fallback():
    script = Path("scripts/generate_observability_docs.py").read_text(encoding="utf-8")

    assert "skip-doxygen" not in script
    assert "Only render Markdown" not in script
    assert "Install doxygen." in script
    assert "re-run with" not in script


def test_committed_observability_markdown_matches_generator():
    from scripts.generate_observability_docs import build_markdown

    generated = build_markdown().strip() + "\n"
    committed = Path("docs/observability/events-metrics.md").read_text(encoding="utf-8")

    assert committed == generated
