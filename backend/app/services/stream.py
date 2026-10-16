"""
backend/app/services/stream.py — Server-Sent Events (SSE) Log Streaming.
Queues logs and streams them in real-time to the frontend via /api/logs/stream.
"""

import asyncio
import json
from typing import AsyncGenerator
from contracts.api_schemas import LogEvent


HEARTBEAT_INTERVAL_SECONDS = 15.0


class SSELogStreamer:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._queues:
            self._queues.remove(q)

    async def broadcast(self, event: LogEvent):
        for q in list(self._queues):
            try:
                await q.put(event)
            except Exception:
                pass

    async def stream_logs(self) -> AsyncGenerator[str, None]:
        q = self.subscribe()
        try:
            # Flush proxy headers before any job exists. SSE comments are ignored
            # by EventSource and never enter the strict LogEvent message channel.
            yield ": connected\n\n"
            while True:
                try:
                    event: LogEvent = await asyncio.wait_for(
                        q.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    # Keep idle connections below the proxy's inactivity timeout.
                    yield ": heartbeat\n\n"
                    continue
                # SSE data formatting
                yield f"data: {event.model_dump_json()}\n\n"
        finally:
            self.unsubscribe(q)


# Global singleton streamer
log_streamer = SSELogStreamer()
