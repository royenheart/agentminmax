import json

from agentminmax.server import ObservationServer


def write_config_with_trace(tmp_path):
    trace = tmp_path / "run.jsonl"
    trace.write_text(
        "\n".join(
            [
                '{"type":"session_start","session_id":"s","timestamp":"2026-06-16T00:00:00Z","model":"m"}',
                '{"type":"token_usage","input_tokens":10,"output_tokens":5}',
                '{"type":"session_end","timestamp":"2026-06-16T00:00:10Z"}',
                "",
            ]
        ),
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
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_api_observation_and_source_refresh(tmp_path):
    config_path = write_config_with_trace(tmp_path)
    app = ObservationServer(config_path=config_path, bundle_dir=tmp_path / "bundle")

    status, payload = app.handle_api("GET", "/api/observation", b"")
    assert status == 200
    assert payload["summary"]["session_count"] == 1
    assert payload["summary"]["total_tokens"] == 15

    status, payload = app.handle_api("POST", "/api/sources/local/refresh", b"")
    assert status == 200
    assert payload["source_id"] == "local"
    assert payload["status"] == "ok"
    assert (tmp_path / "bundle" / "observations.json").exists()


def test_api_sources_and_missing_source_error(tmp_path):
    app = ObservationServer(config_path=write_config_with_trace(tmp_path), bundle_dir=tmp_path / "bundle")

    status, payload = app.handle_api("GET", "/api/sources", b"")
    assert status == 200
    assert payload["sources"][0]["id"] == "local"

    status, payload = app.handle_api("POST", "/api/sources/missing/refresh", b"")
    assert status == 404
    assert payload["error"]["code"] == "source_not_found"


def test_api_command_source_run_records_failure(tmp_path):
    config_path = tmp_path / "agentminmax.toml"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "port = 9999",
                "",
                "[[sources]]",
                'id = "fail"',
                'label = "Fail"',
                'kind = "command"',
                'command = ["python3", "-c", "import sys; sys.exit(7)"]',
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    app = ObservationServer(config_path=config_path, bundle_dir=tmp_path / "bundle")

    status, payload = app.handle_api("POST", "/api/sources/fail/run", b"")

    assert status == 200
    assert payload["status"] == "failed"
    assert payload["returncode"] == 7
    jobs_status, jobs_payload = app.handle_api("GET", "/api/jobs", b"")
    assert jobs_status == 200
    assert jobs_payload["jobs"][0]["source_id"] == "fail"
    assert jobs_payload["jobs"][0]["status"] == "failed"


def test_command_source_run_refreshes_other_configured_sources(tmp_path):
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    output_trace = output_dir / "out.jsonl"
    command = (
        "from pathlib import Path; "
        + f"Path({str(output_trace)!r}).write_text("
        + repr('{"type":"session_start","session_id":"generated","timestamp":"2026-06-16T00:00:00Z"}\\n')
        + ")"
    )
    escaped_command = command.replace('"', '\\"')
    config_path = tmp_path / "agentminmax.toml"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "port = 9999",
                "",
                "[[sources]]",
                'id = "runner"',
                'label = "Runner"',
                'kind = "command"',
                f'command = ["python3", "-c", "{escaped_command}"]',
                "enabled = true",
                "",
                "[[sources]]",
                'id = "generated"',
                'label = "Generated"',
                'kind = "directory"',
                f'path = "{output_dir}"',
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    app = ObservationServer(config_path=config_path, bundle_dir=tmp_path / "bundle")

    status, payload = app.handle_api("POST", "/api/sources/runner/run", b"")

    assert status == 200
    assert payload["status"] == "completed"
    assert app.observation.summary.session_count == 1
    assert app.observation.sessions[0].session_id == "generated"


def test_api_post_sources_updates_config(tmp_path):
    config_path = write_config_with_trace(tmp_path)
    app = ObservationServer(config_path=config_path, bundle_dir=tmp_path / "bundle")
    body = json.dumps(
        {
            "sources": [
                {
                    "id": "manual",
                    "label": "Manual",
                    "kind": "directory",
                    "path": str(tmp_path),
                    "enabled": False,
                    "tags": ["bench"],
                }
            ]
        }
    ).encode()

    status, payload = app.handle_api("POST", "/api/sources", body)

    assert status == 200
    assert payload["sources"][0]["id"] == "manual"
    assert 'id = "manual"' in config_path.read_text(encoding="utf-8")
