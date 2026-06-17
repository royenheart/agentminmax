from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agentminmax.ingest import _short_text


@dataclass(slots=True)
class _MessageStream:
    session_id: str
    item_id: str
    timestamp: str
    start_ms: int
    role: str = "assistant"
    turn_id: str | None = None
    deltas: list[str] = field(default_factory=list)


def load_codex_log_events(path: str | Path, *, source_id: str | None = None) -> list[dict[str, Any]]:
    db_path = Path(path).expanduser()
    if not db_path.exists():
        return []

    streams: dict[tuple[str, str], _MessageStream] = {}
    completed: set[tuple[str, str]] = set()
    events: list[dict[str, Any]] = []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        for row in _iter_received_messages(connection):
            message = _parse_received_message(str(row["feedback_log_body"] or ""))
            if not message:
                continue
            session_id = str(row["thread_id"] or "unknown-thread")
            row_ms = _row_epoch_ms(int(row["ts"]), int(row["ts_nanos"]))
            timestamp = _row_timestamp(int(row["ts"]), int(row["ts_nanos"]))
            message_type = str(message.get("type", ""))

            if message_type == "response.output_item.added":
                item = message.get("item") if isinstance(message.get("item"), dict) else {}
                if item.get("type") != "message" or not item.get("id"):
                    continue
                key = (session_id, str(item["id"]))
                if key in completed:
                    continue
                stream = streams.setdefault(
                    key,
                    _MessageStream(session_id=session_id, item_id=str(item["id"]), timestamp=timestamp, start_ms=row_ms),
                )
                stream.role = str(item.get("role") or stream.role)
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                if metadata.get("turn_id"):
                    stream.turn_id = str(metadata["turn_id"])
                continue

            if message_type == "response.output_text.delta":
                item_id = str(message.get("item_id") or "")
                if not item_id:
                    continue
                key = (session_id, item_id)
                if key in completed:
                    continue
                stream = streams.setdefault(
                    key,
                    _MessageStream(session_id=session_id, item_id=item_id, timestamp=timestamp, start_ms=row_ms),
                )
                delta = message.get("delta")
                if isinstance(delta, str):
                    stream.deltas.append(delta)
                continue

            if message_type == "response.output_text.done":
                item_id = str(message.get("item_id") or "")
                if not item_id:
                    continue
                key = (session_id, item_id)
                if key in completed:
                    continue
                stream = streams.setdefault(
                    key,
                    _MessageStream(session_id=session_id, item_id=item_id, timestamp=timestamp, start_ms=row_ms),
                )
                text = message.get("text")
                if not isinstance(text, str):
                    text = "".join(stream.deltas)
                events.append(_message_stream_event(stream, timestamp, row_ms, text, source_id=source_id))
                completed.add(key)
                streams.pop(key, None)
                continue

            if message_type == "response.output_item.done":
                item = message.get("item") if isinstance(message.get("item"), dict) else {}
                if item.get("type") != "message" or not item.get("id"):
                    continue
                key = (session_id, str(item["id"]))
                if key in completed:
                    continue
                stream = streams.setdefault(
                    key,
                    _MessageStream(session_id=session_id, item_id=str(item["id"]), timestamp=timestamp, start_ms=row_ms),
                )
                stream.role = str(item.get("role") or stream.role)
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                if metadata.get("turn_id"):
                    stream.turn_id = str(metadata["turn_id"])
                events.append(_message_stream_event(stream, timestamp, row_ms, _message_item_text(item), source_id=source_id))
                completed.add(key)
                streams.pop(key, None)

    return events


def _iter_received_messages(connection: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    try:
        return connection.execute(
            """
            SELECT id, ts, ts_nanos, thread_id, feedback_log_body
            FROM logs
            WHERE feedback_log_body LIKE '%Received message %'
            ORDER BY ts, ts_nanos, id
            """
        )
    except sqlite3.DatabaseError:
        return []


def _parse_received_message(body: str) -> dict[str, Any] | None:
    prefix = "Received message "
    start = body.find(prefix)
    if start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(body[start + len(prefix) :].lstrip())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _message_stream_event(
    stream: _MessageStream,
    end_timestamp: str,
    end_ms: int,
    text: str,
    *,
    source_id: str | None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "item_id": stream.item_id,
        "source": "codex_logs",
    }
    if stream.turn_id:
        args["turn_id"] = stream.turn_id
    event = {
        "type": "trace_event",
        "session_id": stream.session_id,
        "timestamp": stream.timestamp,
        "end_timestamp": end_timestamp,
        "duration_ms": max(end_ms - stream.start_ms, 0),
        "category": "message",
        "name": f"{stream.role.title()} stream",
        "phase": "duration",
        "lane": "Messages",
        "status": "ok",
        "summary": _short_text(text),
        "detail": text,
        "args": args,
        "raw_type": "response.output_text.done",
    }
    if source_id is not None:
        event["source_id"] = source_id
    return event


def _message_item_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _row_timestamp(ts: int, ts_nanos: int) -> str:
    microseconds = ts_nanos // 1000
    value = datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=microseconds)
    return value.isoformat().replace("+00:00", "Z")


def _row_epoch_ms(ts: int, ts_nanos: int) -> int:
    return ts * 1000 + ts_nanos // 1_000_000
