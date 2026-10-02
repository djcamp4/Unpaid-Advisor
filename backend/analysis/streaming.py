"""Keep every phase of a long-running SSE response alive."""
import asyncio
import json
import logging
import httpx


def failure_reason(exc):
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "A data service took too long to respond. Please retry."
    if isinstance(exc, (ConnectionError, httpx.RequestError)):
        return "The server could not connect to a data service. Please retry."
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "The server encountered missing or unexpected data. If retrying fails, report this stage."
    return "An unexpected server error stopped the scan. If retrying fails, report this stage."


async def keepalive_stream(source, workers, interval=10):
    pending = None
    stage = "Starting congressional analysis"
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
            if event.startswith("data: "):
                payload = json.loads(event[6:])
                if payload.get("type") == "status":
                    stage = payload.get("message", stage)
            yield event
    except Exception as exc:
        # Exception text can contain provider URLs and credentials.
        logging.error("Congressional scan failed (%s)", type(exc).__name__)
        yield "data: " + json.dumps({
            "type": "error",
            "message": f"Analysis stopped during: {stage} {failure_reason(exc)}",
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
