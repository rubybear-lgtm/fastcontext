import asyncio
from pathlib import Path

import pytest

from fastcontext_mcp import server


def test_explicit_repository_is_passed_to_worker_without_changing_server_cwd(tmp_path, monkeypatch):
    calls = []

    async def worker(request, ctx, **kwargs):
        calls.append((request, kwargs))
        return 'answer'

    monkeypatch.setattr(server, 'run_worker', worker)
    before = Path.cwd()
    assert asyncio.run(server.fastcontext_explore('find code', max_turns=20, work_dir=str(tmp_path))) == 'answer'
    assert calls == [({'query': 'find code', 'max_turns': 10}, {'cwd': str(tmp_path.resolve())})]
    assert Path.cwd() == before


@pytest.mark.parametrize('directory', ['relative/path', '/nonexistent-fastcontext-test-directory'])
def test_invalid_repository_does_not_start_worker(directory, monkeypatch):
    async def worker(*args, **kwargs):
        pytest.fail('invalid scope must fail before loading a worker')

    monkeypatch.setattr(server, 'run_worker', worker)
    with pytest.raises(ValueError):
        asyncio.run(server.fastcontext_explore('find code', work_dir=directory))
