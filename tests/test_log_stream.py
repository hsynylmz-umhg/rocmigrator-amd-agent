"""SSE handshake, idle liveness, strict data frames, and disconnect cleanup."""

import asyncio
import unittest
from typing import AsyncGenerator
from unittest.mock import patch

from backend.app.services import stream
from contracts.api_schemas import LogEvent
from contracts.state_schemas import PipelineState


async def close_stream(generator: AsyncGenerator[str, None]) -> None:
    await generator.aclose()


class TestLogStream(unittest.IsolatedAsyncioTestCase):
    async def test_idle_stream_immediately_emits_connection_comment(self):
        streamer = stream.SSELogStreamer()
        generator = streamer.stream_logs()
        self.addAsyncCleanup(close_stream, generator)

        frame = await asyncio.wait_for(anext(generator), timeout=1.0)

        self.assertEqual(frame, ": connected\n\n")
        self.assertEqual(len(streamer._queues), 1)
        self.assertTrue(streamer._queues[0].empty())
        await generator.aclose()
        self.assertEqual(streamer._queues, [])

    async def test_event_after_handshake_retains_strict_json_and_multiline_text(self):
        streamer = stream.SSELogStreamer()
        generator = streamer.stream_logs()
        self.addAsyncCleanup(close_stream, generator)
        await anext(generator)
        event = LogEvent(
            job_id="stream-job",
            state=PipelineState.COMPILING,
            level="ERROR",
            message="Compiler output:\nunsupported launch assumption\n\ndata: literal text",
        )

        await streamer.broadcast(event)
        frame = await asyncio.wait_for(anext(generator), timeout=1.0)

        self.assertEqual(frame, f"data: {event.model_dump_json()}\n\n")
        self.assertEqual(LogEvent.model_validate_json(frame[6:].strip()), event)
        self.assertEqual(frame.count("\n"), 2)

    async def test_idle_heartbeat_is_a_comment_and_does_not_interrupt_next_event(self):
        streamer = stream.SSELogStreamer()
        generator = streamer.stream_logs()
        self.addAsyncCleanup(close_stream, generator)
        await anext(generator)
        event = LogEvent(
            job_id="heartbeat-job",
            state=PipelineState.CREATED,
            message="Job accepted after an idle connection.",
        )

        with patch.object(stream, "HEARTBEAT_INTERVAL_SECONDS", 0.01):
            heartbeat = await asyncio.wait_for(anext(generator), timeout=1.0)
        self.assertEqual(heartbeat, ": heartbeat\n\n")
        self.assertEqual(len(streamer._queues), 1)

        await streamer.broadcast(event)
        frame = await asyncio.wait_for(anext(generator), timeout=1.0)
        self.assertEqual(LogEvent.model_validate_json(frame[6:].strip()), event)

    async def test_cancelling_a_pending_read_unsubscribes_the_client(self):
        streamer = stream.SSELogStreamer()
        generator = streamer.stream_logs()
        self.addAsyncCleanup(close_stream, generator)
        await anext(generator)
        pending = asyncio.create_task(anext(generator))
        await asyncio.sleep(0)

        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending

        self.assertEqual(streamer._queues, [])

    async def test_closing_one_client_keeps_the_other_subscribed(self):
        streamer = stream.SSELogStreamer()
        first = streamer.stream_logs()
        second = streamer.stream_logs()
        self.addAsyncCleanup(close_stream, first)
        self.addAsyncCleanup(close_stream, second)
        await anext(first)
        await anext(second)
        await first.aclose()
        self.assertEqual(len(streamer._queues), 1)
        event = LogEvent(
            job_id="remaining-client",
            state=PipelineState.HIPIFICATION,
            message="The remaining subscriber receives this event.",
        )

        await streamer.broadcast(event)
        frame = await asyncio.wait_for(anext(second), timeout=1.0)

        self.assertEqual(LogEvent.model_validate_json(frame[6:].strip()), event)
        await second.aclose()
        self.assertEqual(streamer._queues, [])


if __name__ == "__main__":
    unittest.main()
