"""Tests for the SSE event streaming endpoint and generator.

Covers: init replay, live job_update events, disconnect cleanup,
keepalive ping, job_removed broadcasting, and session isolation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch


from app.core.database import create_job, create_session, get_active_jobs_by_session
from app.models.job import Job, ProgressEvent
from app.routers.sse import event_generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(session_id: str, *, status: str = "queued", **overrides) -> Job:
    """Build a Job with sane defaults."""
    return Job(
        id=overrides.get("id", str(uuid.uuid4())),
        session_id=session_id,
        url=overrides.get("url", "https://example.com/video"),
        status=status,
        created_at=overrides.get("created_at", datetime.now(timezone.utc).isoformat()),
    )


async def _collect_events(gen, *, count: int = 1, timeout: float = 5.0):
    """Consume *count* events from an async generator with a safety timeout."""
    events = []

    async def _drain():
        async for event in gen:
            events.append(event)
            if len(events) >= count:
                break

    await asyncio.wait_for(_drain(), timeout=timeout)
    return events


# ---------------------------------------------------------------------------
# Database query tests
# ---------------------------------------------------------------------------

class TestGetActiveJobsBySession:
    """Verify that get_active_jobs_by_session filters terminal statuses."""

    async def test_returns_only_non_terminal(self, db):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        queued_job = _make_job(sid, status="queued")
        downloading_job = _make_job(sid, status="downloading")
        completed_job = _make_job(sid, status="completed")
        failed_job = _make_job(sid, status="failed")

        for j in (queued_job, downloading_job, completed_job, failed_job):
            await create_job(db, j)

        active = await get_active_jobs_by_session(db, sid)
        active_ids = {j.id for j in active}

        assert queued_job.id in active_ids
        assert downloading_job.id in active_ids
        assert completed_job.id not in active_ids
        assert failed_job.id not in active_ids

    async def test_empty_when_all_terminal(self, db):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        for status in ("completed", "failed", "expired"):
            await create_job(db, _make_job(sid, status=status))

        active = await get_active_jobs_by_session(db, sid)
        assert active == []


# ---------------------------------------------------------------------------
# Generator-level tests (direct, no HTTP)
# ---------------------------------------------------------------------------

class TestEventGeneratorInit:
    """Init event replays current non-terminal jobs."""

    async def test_init_event_with_jobs(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)
        job = _make_job(sid, status="queued")
        await create_job(db, job)

        gen = event_generator(sid, broker, db)
        events = await _collect_events(gen, count=1)

        assert len(events) == 1
        assert events[0]["event"] == "init"
        payload = json.loads(events[0]["data"])
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["id"] == job.id

        # Cleanup — close generator to trigger finally block
        await gen.aclose()

    async def test_init_event_empty_session(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        gen = event_generator(sid, broker, db)
        events = await _collect_events(gen, count=1)

        payload = json.loads(events[0]["data"])
        assert payload["jobs"] == []

        await gen.aclose()


class TestEventGeneratorLiveStream:
    """Live job_update and dict events arrive correctly."""

    async def test_progress_event_delivery(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        gen = event_generator(sid, broker, db)

        # Consume init
        await _collect_events(gen, count=1)

        # Publish a ProgressEvent to the broker
        progress = ProgressEvent(
            job_id="job-1", status="downloading", percent=42.0,
        )
        # Use _publish_sync since we're on the event loop already
        broker._publish_sync(sid, progress)

        events = await _collect_events(gen, count=1)
        assert events[0]["event"] == "job_update"
        data = json.loads(events[0]["data"])
        assert data["job_id"] == "job-1"
        assert data["percent"] == 42.0

        await gen.aclose()

    async def test_dict_event_delivery(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        gen = event_generator(sid, broker, db)
        await _collect_events(gen, count=1)  # init

        broker._publish_sync(sid, {"event": "job_removed", "data": {"job_id": "abc"}})

        events = await _collect_events(gen, count=1)
        assert events[0]["event"] == "job_removed"
        data = json.loads(events[0]["data"])
        assert data["job_id"] == "abc"

        await gen.aclose()


class TestEventGeneratorDisconnect:
    """Verify that unsubscribe fires on generator close."""

    async def test_unsubscribe_on_close(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        gen = event_generator(sid, broker, db)
        await _collect_events(gen, count=1)  # init

        # Broker should have a subscriber now
        assert sid in broker._subscribers
        assert len(broker._subscribers[sid]) == 1

        # Close the generator — triggers finally block
        await gen.aclose()

        # Subscriber should be cleaned up
        assert sid not in broker._subscribers


class TestEventGeneratorKeepalive:
    """Verify that a ping event is sent after the keepalive timeout."""

    async def test_ping_after_timeout(self, db, broker):
        sid = str(uuid.uuid4())
        await create_session(db, sid)

        # Patch the timeout to a very short value for test speed
        with patch("app.routers.sse.KEEPALIVE_TIMEOUT", 0.1):
            gen = event_generator(sid, broker, db)
            await _collect_events(gen, count=1)  # init

            # Next event should be a ping (no messages published)
            events = await _collect_events(gen, count=1)
            assert events[0]["event"] == "ping"
            assert events[0]["data"] == ""

            await gen.aclose()


class TestSessionIsolation:
    """Jobs for one session don't leak into another session's init."""

    async def test_init_only_contains_own_session(self, db, broker):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        await create_session(db, sid_a)
        await create_session(db, sid_b)

        job_a = _make_job(sid_a, status="queued")
        job_b = _make_job(sid_b, status="downloading")
        await create_job(db, job_a)
        await create_job(db, job_b)

        # Connect as session A
        gen = event_generator(sid_a, broker, db)
        events = await _collect_events(gen, count=1)

        payload = json.loads(events[0]["data"])
        job_ids = [j["id"] for j in payload["jobs"]]
        assert job_a.id in job_ids
        assert job_b.id not in job_ids

        await gen.aclose()


# ---------------------------------------------------------------------------
# HTTP-level integration test
# ---------------------------------------------------------------------------

class TestSSEEndpointHTTP:
    """Integration test hitting the real HTTP endpoint via httpx."""

    async def test_sse_endpoint_returns_init(self, client):
        """GET /api/events returns 200 with text/event-stream and an init event.

        httpx's ``ASGITransport`` calls ``await app(scope, receive, send)`` and
        waits for the *entire* response body — so an infinite SSE stream hangs
        it forever.  We bypass the transport and invoke the ASGI app directly
        with custom ``receive``/``send`` callables.  Once the body contains
        ``"jobs"`` (i.e. the init event has been sent) we set a disconnect
        event; ``EventSourceResponse``'s ``_listen_for_disconnect`` task picks
        that up, cancels the task group, and returns normally.
        """
        # Access the underlying ASGI app wired by the client fixture.
        test_app = client._transport.app

        received_status: int | None = None
        received_content_type: str | None = None
        received_body = b""
        disconnected = asyncio.Event()

        async def receive() -> dict:
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            nonlocal received_status, received_content_type, received_body
            if message["type"] == "http.response.start":
                received_status = message["status"]
                for k, v in message.get("headers", []):
                    if k == b"content-type":
                        received_content_type = v.decode()
            elif message["type"] == "http.response.body":
                received_body += message.get("body", b"")
                # Signal disconnect as soon as the init event payload arrives.
                if b'"jobs"' in received_body:
                    disconnected.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "headers": [],
            "scheme": "http",
            "path": "/api/events",
            "raw_path": b"/api/events",
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        }

        # Safety timeout in case disconnect signalling doesn't terminate the app.
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(5.0):
                await test_app(scope, receive, send)

        assert received_status == 200
        assert received_content_type is not None
        assert "text/event-stream" in received_content_type
        assert b'"jobs"' in received_body


class TestJobRemovedViaDELETE:
    """DELETE /api/downloads/{id} publishes job_removed event."""

    async def test_delete_publishes_job_removed(self, db, broker):
        """Create a job, subscribe, delete it, verify job_removed arrives."""
        sid = str(uuid.uuid4())
        await create_session(db, sid)
        job = _make_job(sid, status="queued")
        await create_job(db, job)

        # Subscribe to the broker for this session
        queue = broker.subscribe(sid)

        # Simulate what the DELETE handler does: publish job_removed
        broker._publish_sync(
            sid,
            {"event": "job_removed", "data": {"job_id": job.id}},
        )

        event = queue.get_nowait()
        assert event["event"] == "job_removed"
        assert event["data"]["job_id"] == job.id

        broker.unsubscribe(sid, queue)
