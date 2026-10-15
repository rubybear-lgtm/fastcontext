import asyncio
from types import SimpleNamespace

import pytest

from fastcontext_mcp.engine import run_agent
from fastcontext_mcp.sources import ExplorationError


class Context:
    def __init__(self):
        self.messages = []

    async def add(self, message):
        self.messages.extend(message if isinstance(message, list) else [message])

    def get_messages(self):
        return self.messages


class Tools:
    def __init__(self):
        self.read = False

    async def orient(self, query):
        return 'Repository root: /repo\n' + query

    def schema_list(self):
        return []

    def receipts(self):
        return '/repo/file.py:1-3' if self.read else 'No source content has been observed.'

    def verified_subset(self, answer):
        return '/repo/file.py:1-3' if self.read and answer == 'mixed' else ''

    async def call(self, message):
        self.read = message.tool_calls[0].name == 'Read'
        return [SimpleNamespace(role='tool', content='actual source' if self.read else 'Tool error')]

    def validate(self, answer):
        if not self.read or answer != 'verified':
            raise ExplorationError('no observed source')
        return '/repo/file.py:1-3'


def agent_with(responses):
    async def acall(**kwargs):
        return next(responses)
    return SimpleNamespace(
        system_prompt='system', work_dir='/repo', context=Context(),
        toolset=Tools(), llm=SimpleNamespace(acall=acall),
    )


def answer(content):
    return SimpleNamespace(role='assistant', content=content, tool_calls=[])


def test_no_evidence_never_returns_success():
    agent = agent_with(iter([answer('made up'), answer('made up')]))
    with pytest.raises(ExplorationError, match='could not verify'):
        asyncio.run(run_agent(agent, 'query', 1, None, SimpleNamespace))
    assert any('Answer rejected' in msg.content for msg in agent.context.messages)


def test_rejected_final_answer_can_recover_with_real_evidence():
    call = SimpleNamespace(role='assistant', content=None, tool_calls=[SimpleNamespace(name='Read', arguments='{"path":"file.py"}', id='one')])
    agent = agent_with(iter([answer('made up'), call, answer('verified')]))
    result, steps = asyncio.run(run_agent(agent, 'query', 2, None, SimpleNamespace))
    assert result == '/repo/file.py:1-3'
    assert steps == ['[turn 2] Read file.py']


def test_tool_budget_is_bounded_even_when_model_keeps_calling_tools():
    call = SimpleNamespace(role='assistant', content=None, tool_calls=[SimpleNamespace(name='Read', arguments='bad json', id='one')])
    agent = agent_with(iter([call, call]))
    with pytest.raises(ExplorationError, match='tool budget'):
        asyncio.run(run_agent(agent, 'query', 1, None, SimpleNamespace))


def test_budget_exhaustion_can_return_only_verified_partial_citations():
    call = SimpleNamespace(role='assistant', content=None, tool_calls=[SimpleNamespace(name='Read', arguments='{"path":"file.py"}', id='one')])
    agent = agent_with(iter([call, answer('mixed')]))
    result, _ = asyncio.run(run_agent(agent, 'query', 1, None, SimpleNamespace))
    assert result.startswith('Partial exploration:')
    assert result.endswith('/repo/file.py:1-3')
    assert 'mixed' not in result
