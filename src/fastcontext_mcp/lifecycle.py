"""Request-scoped inference subprocesses, with cancellation and parent-death cleanup."""

import asyncio
import json
import os
import signal
import sys


async def run_worker(request, ctx=None, *, command=None, timeout=600, cwd=None):
    """Keep stdin open as a parent-liveness signal; reap the worker on every exit."""
    process = await asyncio.create_subprocess_exec(
        *(command or [sys.executable, "-m", "fastcontext_mcp.worker"]),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        # Inherit stderr for diagnostics; never let MLX logs corrupt MCP stdout.
        stderr=None,
        start_new_session=True,
        limit=4 * 1024 * 1024,
        cwd=cwd,
    )
    try:
        async with asyncio.timeout(timeout):
            process.stdin.write((json.dumps(request) + "\n").encode())
            await process.stdin.drain()
            result = None
            async for line in process.stdout:
                event = json.loads(line)
                if "error" in event:
                    raise RuntimeError(f"FastContext exploration failed: {event['error']}")
                if "result" in event:
                    result = event["result"]
                elif ctx:
                    try:
                        await ctx.report_progress(
                            event["progress"], event["total"], event["message"]
                        )
                    except Exception:
                        pass
            status = await process.wait()
            if status != 0 or result is None:
                raise RuntimeError(f"FastContext worker exited without a result (status {status})")
            return result
    finally:
        process.stdin.close()
        # Include any tool subprocesses in cleanup, even if the worker has exited.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
