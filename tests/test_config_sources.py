from pathlib import Path

from agentminmax.config import BenchmarkSource, load_config, save_config
from agentminmax.sources import load_source_events


def test_load_config_round_trip_expands_jsonl_glob(tmp_path):
    trace = tmp_path / "run.jsonl"
    trace.write_text(
        '{"type":"session_start","session_id":"s","timestamp":"2026-06-16T00:00:00Z"}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "agentminmax.toml"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "port = 9999",
                "",
                "[[sources]]",
                'id = "local"',
                'label = "Local"',
                'kind = "jsonl_glob"',
                f'path = "{trace}"',
                "enabled = true",
                'tags = ["daily"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)
    save_config(config, config_path)
    reloaded = load_config(config_path)
    events = load_source_events(reloaded.sources[0])

    assert reloaded.server.port == 9999
    assert reloaded.sources[0].id == "local"
    assert reloaded.sources[0].tags == ["daily"]
    assert events[0]["type"] == "session_start"
    assert events[0]["source_id"] == "local"


def test_directory_source_recursively_reads_jsonl_files(tmp_path):
    nested = tmp_path / "runs" / "nested"
    nested.mkdir(parents=True)
    (nested / "a.jsonl").write_text('{"type":"message","content":"a"}\n', encoding="utf-8")
    (nested / "ignore.txt").write_text('{"type":"message","content":"ignored"}\n', encoding="utf-8")
    source = BenchmarkSource(
        id="dir",
        label="Directory",
        kind="directory",
        path=str(tmp_path / "runs"),
        enabled=True,
    )

    events = load_source_events(source)

    assert [event["content"] for event in events] == ["a"]
    assert events[0]["source_id"] == "dir"


def test_disabled_source_returns_no_events(tmp_path):
    trace = tmp_path / "run.jsonl"
    trace.write_text('{"type":"message","content":"a"}\n', encoding="utf-8")
    source = BenchmarkSource(id="off", label="Off", kind="jsonl_glob", path=str(trace), enabled=False)

    assert load_source_events(source) == []
