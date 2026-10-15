import asyncio
import os
import subprocess
import sys

import pytest

from fastcontext_mcp.lifecycle import run_worker


def test_server_import_does_not_load_inference_runtime():
    subprocess.run(
        [sys.executable, "-c", "import sys; import fastcontext_mcp.server; assert 'mlx.core' not in sys.modules; assert 'mlx_lm' not in sys.modules"],
        check=True,
    )


def test_worker_result_progress_and_exit(tmp_path):
    pid_file = tmp_path / "pid"
    code = f'''
import json, os, sys
from pathlib import Path
Path({str(pid_file)!r}).write_text(str(os.getpid()))
request = json.loads(sys.stdin.readline())
print(json.dumps({{"progress": 1, "total": 1, "message": "done"}}), flush=True)
print(json.dumps({{"result": request["query"]}}), flush=True)
'''
    events = []

    class Context:
        async def report_progress(self, *args):
            events.append(args)

    result = asyncio.run(run_worker({"query": "answer"}, Context(), command=[sys.executable, "-c", code]))
    assert result == "answer"
    assert events == [(1, 1, "done")]
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancellation_reap_worker(tmp_path, cancel):
    pid_file = tmp_path / "pid"
    code = f'import os, time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)'

    async def exercise():
        task = asyncio.create_task(run_worker({}, command=[sys.executable, "-c", code], timeout=1))
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_file.exists()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task

    asyncio.run(exercise())
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_worker_failure_is_reported():
    with pytest.raises(RuntimeError, match="status 7"):
        asyncio.run(run_worker({}, command=[sys.executable, "-c", "import sys; sys.exit(7)"]))


def test_worker_runs_in_selected_repository(tmp_path):
    result = asyncio.run(run_worker({}, cwd=str(tmp_path), command=[
        sys.executable, "-c",
        'import json, os, sys; sys.stdin.readline(); print(json.dumps({"result": os.getcwd()}))',
    ]))
    assert result == str(tmp_path.resolve())


def test_worker_evidence_error_is_returned_to_caller():
    command = [sys.executable, '-c', 'import json,sys; sys.stdin.readline(); print(json.dumps({"error":"No source-backed citations were produced"}))']
    with pytest.raises(RuntimeError, match='No source-backed citations were produced'):
        asyncio.run(run_worker({}, command=command))
