from agentminmax.models import AgentSession, ModelInfo, TraceEvent
from agentminmax.traces import session_chrome_trace


def test_chrome_trace_export_packs_overlapping_duration_events_for_perfetto():
    session = AgentSession(
        session_id="parallel-tools",
        agent="codex",
        model=ModelInfo(name="gpt-5"),
        trace_events=[
            TraceEvent(
                event_id="tool-1",
                category="tool",
                name="exec_command",
                phase="duration",
                timestamp="2026-06-17T00:00:00Z",
                duration_ms=100,
                lane="Tool Calls",
            ),
            TraceEvent(
                event_id="tool-2",
                category="tool",
                name="apply_patch",
                phase="duration",
                timestamp="2026-06-17T00:00:00.050Z",
                duration_ms=100,
                lane="Tool Calls",
            ),
        ],
    )

    trace = session_chrome_trace(session)

    slices = [event for event in trace["traceEvents"] if event.get("ph") == "X"]
    assert len(slices) == 2
    assert slices[0]["tid"] != slices[1]["tid"]


def test_chrome_trace_export_treats_duration_ms_as_timeline_block():
    session = AgentSession(
        session_id="duration-from-source",
        agent="codex",
        model=ModelInfo(name="gpt-5"),
        trace_events=[
            TraceEvent(
                event_id="info-1",
                category="message",
                name="Tool summary",
                phase="instant",
                timestamp="2026-06-17T00:00:00Z",
                duration_ms=250,
                lane="Messages",
            ),
        ],
    )

    trace = session_chrome_trace(session)

    block = next(event for event in trace["traceEvents"] if event.get("name") == "Tool summary")
    assert block["ph"] == "X"
    assert block["dur"] == 250000


def test_chrome_trace_export_renders_messages_and_tokens_as_visible_slices():
    session = AgentSession(
        session_id="visible-events",
        agent="codex",
        model=ModelInfo(name="gpt-5"),
        trace_events=[
            TraceEvent(
                event_id="message-1",
                category="message",
                name="Assistant message",
                phase="instant",
                timestamp="2026-06-17T00:00:00Z",
                lane="Messages",
                summary="hello",
            ),
            TraceEvent(
                event_id="tokens-1",
                category="tokens",
                name="Token usage",
                phase="counter",
                timestamp="2026-06-17T00:00:01Z",
                lane="Token Usage",
                tokens={"input": 100, "output": 20, "cached_input": 50},
            ),
        ],
    )

    trace = session_chrome_trace(session)

    message = next(event for event in trace["traceEvents"] if event.get("name") == "Assistant message")
    tokens = next(event for event in trace["traceEvents"] if event.get("name") == "Token usage")
    assert message["ph"] == "X"
    assert message["dur"] > 0
    assert tokens["ph"] == "X"
    assert tokens["dur"] > 0
    assert tokens["args"]["tokens"]["input"] == 100


def test_chrome_trace_export_adds_token_counter_tracks_for_perfetto_alignment():
    session = AgentSession(
        session_id="token-counters",
        agent="codex",
        model=ModelInfo(name="gpt-5"),
        trace_events=[
            TraceEvent(
                event_id="tokens-1",
                category="tokens",
                name="Token usage",
                phase="counter",
                timestamp="2026-06-17T00:00:01Z",
                lane="Token Usage",
                tokens={"input": 100, "output": 20, "cached_input": 50},
            ),
            TraceEvent(
                event_id="tokens-2",
                category="tokens",
                name="Token usage",
                phase="counter",
                timestamp="2026-06-17T00:00:03Z",
                lane="Token Usage",
                tokens={"input": 180, "output": 45, "cached_input": 80},
            ),
        ],
    )

    trace = session_chrome_trace(session)

    counters = [event for event in trace["traceEvents"] if event.get("ph") == "C"]
    assert {event["name"] for event in counters} == {
        "Token Input",
        "Token Output",
        "Token Cached Input",
        "Token Total",
    }
    assert [event["args"]["value"] for event in counters if event["name"] == "Token Input"] == [100, 180]
    assert [event["args"]["value"] for event in counters if event["name"] == "Token Output"] == [20, 45]
    assert [event["args"]["value"] for event in counters if event["name"] == "Token Cached Input"] == [50, 80]
    assert [event["args"]["value"] for event in counters if event["name"] == "Token Total"] == [120, 225]
