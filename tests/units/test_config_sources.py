from pathlib import Path
import json
import sqlite3

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


def test_codex_logs_source_builds_message_stream_duration_events(tmp_path):
    db_path = tmp_path / "logs_2.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          ts_nanos INTEGER NOT NULL,
          level TEXT NOT NULL,
          target TEXT NOT NULL,
          feedback_log_body TEXT,
          module_path TEXT,
          file TEXT,
          line INTEGER,
          thread_id TEXT,
          process_uuid TEXT,
          estimated_bytes INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    def insert_message(ts: int, ts_nanos: int, payload: dict) -> None:
        connection.execute(
            """
            INSERT INTO logs (ts, ts_nanos, level, target, feedback_log_body, thread_id, process_uuid)
            VALUES (?, ?, 'INFO', 'log', ?, 'thread-1', 'process-1')
            """,
            (ts, ts_nanos, f"Received message {json.dumps(payload)}"),
        )

    insert_message(
        1_787_221_200,
        100_000_000,
        {
            "type": "response.output_item.added",
            "item": {"id": "msg-1", "type": "message", "role": "assistant", "metadata": {"turn_id": "turn-1"}},
        },
    )
    insert_message(
        1_787_221_201,
        0,
        {
            "type": "response.output_text.delta",
            "item_id": "msg-1",
            "output_index": 0,
            "content_index": 0,
            "delta": "Hello",
        },
    )
    insert_message(
        1_787_221_203,
        250_000_000,
        {
            "type": "response.output_text.done",
            "item_id": "msg-1",
            "output_index": 0,
            "content_index": 0,
            "text": "Hello world",
        },
    )
    connection.commit()
    connection.close()
    source = BenchmarkSource(id="codex-log", label="Codex Log", kind="codex_logs", path=str(db_path), enabled=True)

    events = load_source_events(source)

    assert len(events) == 1
    event = events[0]
    assert event["type"] == "trace_event"
    assert event["source_id"] == "codex-log"
    assert event["session_id"] == "thread-1"
    assert event["category"] == "message"
    assert event["phase"] == "duration"
    assert event["timestamp"] == "2026-08-20T10:20:00.100000Z"
    assert event["end_timestamp"] == "2026-08-20T10:20:03.250000Z"
    assert event["duration_ms"] == 3150
    assert event["args"]["turn_id"] == "turn-1"
    assert event["detail"] == "Hello world"


def test_codex_logs_source_uses_output_item_done_when_text_done_is_missing(tmp_path):
    db_path = tmp_path / "logs_2.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          ts_nanos INTEGER NOT NULL,
          level TEXT NOT NULL,
          target TEXT NOT NULL,
          feedback_log_body TEXT,
          module_path TEXT,
          file TEXT,
          line INTEGER,
          thread_id TEXT,
          process_uuid TEXT,
          estimated_bytes INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO logs (ts, ts_nanos, level, target, feedback_log_body, thread_id, process_uuid)
        VALUES (?, ?, 'INFO', 'log', ?, 'thread-2', 'process-1')
        """,
        (
            1_787_221_200,
            0,
            'Received message {"type":"response.output_text.delta","item_id":"msg-2","delta":"Partial"}',
        ),
    )
    connection.execute(
        """
        INSERT INTO logs (ts, ts_nanos, level, target, feedback_log_body, thread_id, process_uuid)
        VALUES (?, ?, 'INFO', 'log', ?, 'thread-2', 'process-1')
        """,
        (
            1_787_221_204,
            0,
            "Received message "
            + json.dumps(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": "msg-2",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "metadata": {"turn_id": "turn-2"},
                        "content": [{"type": "output_text", "text": "Final message"}],
                    },
                }
            ),
        ),
    )
    connection.commit()
    connection.close()
    source = BenchmarkSource(id="codex-log", label="Codex Log", kind="codex_logs", path=str(db_path), enabled=True)

    events = load_source_events(source)

    assert len(events) == 1
    assert events[0]["session_id"] == "thread-2"
    assert events[0]["duration_ms"] == 4000
    assert events[0]["detail"] == "Final message"
    assert events[0]["args"]["turn_id"] == "turn-2"


def test_codex_logs_source_parses_received_messages_with_span_prefix(tmp_path):
    db_path = tmp_path / "logs_2.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          ts_nanos INTEGER NOT NULL,
          level TEXT NOT NULL,
          target TEXT NOT NULL,
          feedback_log_body TEXT,
          module_path TEXT,
          file TEXT,
          line INTEGER,
          thread_id TEXT,
          process_uuid TEXT,
          estimated_bytes INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    body = (
        'session_loop{thread_id=thread-3}:submission_dispatch '
        'Received message {"type":"response.output_text.done","item_id":"msg-3","text":"Prefixed"}'
    )
    connection.execute(
        """
        INSERT INTO logs (ts, ts_nanos, level, target, feedback_log_body, thread_id, process_uuid)
        VALUES (?, ?, 'INFO', 'log', ?, 'thread-3', 'process-1')
        """,
        (1_787_221_205, 0, body),
    )
    connection.commit()
    connection.close()
    source = BenchmarkSource(id="codex-log", label="Codex Log", kind="codex_logs", path=str(db_path), enabled=True)

    events = load_source_events(source)

    assert len(events) == 1
    assert events[0]["session_id"] == "thread-3"
    assert events[0]["detail"] == "Prefixed"


def test_disabled_source_returns_no_events(tmp_path):
    trace = tmp_path / "run.jsonl"
    trace.write_text('{"type":"message","content":"a"}\n', encoding="utf-8")
    source = BenchmarkSource(id="off", label="Off", kind="jsonl_glob", path=str(trace), enabled=False)

    assert load_source_events(source) == []


def test_missing_config_defaults_to_codex_home_and_runs_sources(tmp_path):
    config = load_config(tmp_path / "missing.toml")

    assert [(source.id, source.kind, source.path) for source in config.sources] == [
        ("local-codex", "codex_home", "$CODEX_HOME"),
        ("benchmark-runs", "runs", "runs"),
    ]
