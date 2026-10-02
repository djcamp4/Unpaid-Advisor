"""Keep every phase of a long-running SSE response alive."""
import asyncio
import json
import logging


async def keepalive_stream(source, workers, interval=10):
    pending = None
    try:
        while True:
            pending = asyncio.create_task(anext(source))
            while not pending.done():
                done, _ = await asyncio.wait({pending}, timeout=interval)
                if not done:
                    yield ": keepalive\n\n"
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield event
    except Exception as exc:
        # Exception text can contain provider URLs and credentials.
        logging.error("Congressional scan failed (%s)", type(exc).__name__)
        yield "data: " + json.dumps({
            "type": "error",
            "message": "Congressional analysis could not finish. Please try again.",
        }) + "\n\n"
    finally:
        tasks = list(workers)
        if pending is not None:
            tasks.append(pending)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await source.aclose()
