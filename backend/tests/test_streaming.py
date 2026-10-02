import asyncio
import json
import unittest

from analysis.streaming import keepalive_stream


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_phase_keeps_alive_without_restarting_work(self):
        release = asyncio.Event()
        calls = []
        async def source():
            calls.append(1)
            await release.wait()
            yield 'data: {"type":"complete"}\n\n'
        stream = keepalive_stream(source(), [], interval=0.01)
        self.assertEqual(await anext(stream), ': keepalive\n\n')
        self.assertEqual(await anext(stream), ': keepalive\n\n')
        release.set()
        self.assertIn('complete', await anext(stream))
        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertEqual(calls, [1])

    async def test_exception_becomes_safe_error_event(self):
        async def source():
            yield 'data: {"type":"status","message":"Rule engine: 11–20"}\n\n'
            raise ValueError('secret-provider-url')
        events = [event async for event in keepalive_stream(source(), [])]
        self.assertEqual(json.loads(events[-1][6:])['type'], 'error')
        self.assertNotIn('secret-provider-url', ''.join(events))
        self.assertIn('Rule engine: 11', events[-1])
        self.assertIn('unexpected data', events[-1])

    async def test_disconnect_closes_source_and_workers(self):
        closed = asyncio.Event()
        worker = asyncio.create_task(asyncio.sleep(100))
        async def source():
            try:
                await asyncio.sleep(100)
                yield 'unreachable'
            finally:
                closed.set()
        stream = keepalive_stream(source(), [worker], interval=0.01)
        await anext(stream)
        await stream.aclose()
        self.assertTrue(closed.is_set())
        self.assertTrue(worker.cancelled())
