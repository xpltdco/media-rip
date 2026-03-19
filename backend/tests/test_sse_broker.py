"""Tests for the SSE broker — including thread-safe publish."""

from __future__ import annotations

import asyncio
import threading


from app.core.sse_broker import SSEBroker


class TestSubscription:
    """Subscribe / unsubscribe lifecycle."""

    async def test_subscribe_creates_queue(self, broker: SSEBroker):
        queue = broker.subscribe("sess-1")
        assert isinstance(queue, asyncio.Queue)
        assert queue.empty()

    async def test_unsubscribe_removes_queue(self, broker: SSEBroker):
        queue = broker.subscribe("sess-1")
        broker.unsubscribe("sess-1", queue)
        # Internal state should be clean
        assert "sess-1" not in broker._subscribers

    async def test_unsubscribe_nonexistent_session(self, broker: SSEBroker):
        """Unsubscribing from a session that was never subscribed should not raise."""
        fake_queue: asyncio.Queue = asyncio.Queue()
        broker.unsubscribe("ghost-session", fake_queue)  # no error


class TestPublish:
    """Event delivery to subscribers."""

    async def test_publish_delivers_to_subscriber(self, broker: SSEBroker):
        queue = broker.subscribe("sess-1")
        event = {"type": "progress", "percent": 50}

        broker._publish_sync("sess-1", event)

        received = queue.get_nowait()
        assert received == event

    async def test_multiple_subscribers_receive_event(self, broker: SSEBroker):
        q1 = broker.subscribe("sess-1")
        q2 = broker.subscribe("sess-1")

        event = {"type": "done"}
        broker._publish_sync("sess-1", event)

        assert q1.get_nowait() == event
        assert q2.get_nowait() == event

    async def test_publish_to_nonexistent_session_no_error(self, broker: SSEBroker):
        """Fire-and-forget to a session with no subscribers."""
        broker._publish_sync("nobody-home", {"type": "test"})  # no error

    async def test_unsubscribed_queue_does_not_receive(self, broker: SSEBroker):
        queue = broker.subscribe("sess-1")
        broker.unsubscribe("sess-1", queue)

        broker._publish_sync("sess-1", {"type": "after-unsub"})
        assert queue.empty()


class TestThreadSafePublish:
    """Verify publish() works correctly from a non-asyncio thread."""

    async def test_publish_from_worker_thread(self, broker: SSEBroker):
        """Simulate a yt-dlp worker thread calling broker.publish()."""
        queue = broker.subscribe("sess-1")
        event = {"type": "progress", "percent": 75}

        # Fire publish from a real OS thread (like yt-dlp workers do)
        thread = threading.Thread(
            target=broker.publish,
            args=("sess-1", event),
        )
        thread.start()
        thread.join(timeout=2.0)

        # Give the event loop a tick to process the call_soon_threadsafe callback
        await asyncio.sleep(0.05)

        assert not queue.empty()
        received = queue.get_nowait()
        assert received == event

    async def test_multiple_thread_publishes(self, broker: SSEBroker):
        """Multiple threads publishing concurrently to the same session."""
        queue = broker.subscribe("sess-1")
        events = [{"i": i} for i in range(5)]
        threads = []

        for ev in events:
            t = threading.Thread(target=broker.publish, args=("sess-1", ev))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        await asyncio.sleep(0.1)

        received = []
        while not queue.empty():
            received.append(queue.get_nowait())

        assert len(received) == 5
        # All events arrived (order may vary)
        assert {r["i"] for r in received} == {0, 1, 2, 3, 4}
