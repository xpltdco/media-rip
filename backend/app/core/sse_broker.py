"""Server-Sent Events broker for per-session event distribution.

The broker holds one list of ``asyncio.Queue`` per session.  Download
workers running on a :pymod:`concurrent.futures` thread call
:meth:`publish` which uses ``loop.call_soon_threadsafe`` to marshal the
event onto the asyncio event loop — making it safe to call from any thread.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("mediarip.sse")


class SSEBroker:
    """Thread-safe pub/sub for SSE events, keyed by session ID."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # ------------------------------------------------------------------
    # Subscription management (called from the asyncio thread)
    # ------------------------------------------------------------------

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """Create and return a new queue for *session_id*."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(queue)
        logger.debug("Subscriber added for session %s (total: %d)",
                      session_id, len(self._subscribers[session_id]))
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Remove *queue* from *session_id*'s subscriber list."""
        queues = self._subscribers.get(session_id)
        if queues is None:
            return
        try:
            queues.remove(queue)
        except ValueError:
            pass
        if not queues:
            del self._subscribers[session_id]
        logger.debug("Subscriber removed for session %s", session_id)

    # ------------------------------------------------------------------
    # Publishing (safe to call from ANY thread)
    # ------------------------------------------------------------------

    def publish(self, session_id: str, event: object) -> None:
        """Schedule event delivery on the event loop — thread-safe.

        This is the primary entry point for download worker threads.
        """
        self._loop.call_soon_threadsafe(self._publish_sync, session_id, event)

    def publish_all(self, event: object) -> None:
        """Publish *event* to ALL sessions — thread-safe.

        Used for broadcasts like purge notifications.
        """
        self._loop.call_soon_threadsafe(self._publish_all_sync, event)

    def _publish_all_sync(self, event: object) -> None:
        """Deliver *event* to all queues across all sessions."""
        for session_id, queues in self._subscribers.items():
            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(
                        "Queue full for session %s — dropping broadcast", session_id
                    )

    def _publish_sync(self, session_id: str, event: object) -> None:
        """Deliver *event* to all queues for *session_id*.

        Runs on the event loop thread (scheduled via ``call_soon_threadsafe``).
        Silently skips sessions with no subscribers so yt-dlp workers can
        fire-and-forget without checking subscription state.
        """
        queues = self._subscribers.get(session_id)
        if not queues:
            return
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Queue full for session %s — dropping event", session_id
                )
