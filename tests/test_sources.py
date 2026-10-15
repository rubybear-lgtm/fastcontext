import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest

from fastcontext_mcp.sources import ExplorationError, SourceTools, find_ripgrep


@pytest.fixture
def sources(tmp_path):
    if not shutil.which('rg'):
        pytest.skip('ripgrep required for live source-tool tests')
    (tmp_path / '.git').mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/auth.php').write_text("<?php\n'default' => 'web',\n'driver' => 'session',\n")
    return SourceTools(tmp_path, SimpleNamespace)


def test_ripgrep_is_discovered_instead_of_hardcoded(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda command: '/custom/bin/rg')
    assert find_ripgrep() == '/custom/bin/rg'
    monkeypatch.setattr(shutil, 'which', lambda command: None)
    with pytest.raises(ExplorationError, match='unavailable on PATH'):
        find_ripgrep()


def test_read_resolves_relative_paths_and_records_only_observed_lines(sources):
    result = asyncio.run(sources.invoke('Read', {'path': 'config/auth.php', 'offset': 2, 'limit': 1}))
    assert "2|'default' => 'web'," in result
    assert sources.validate('config/auth.php:2-2 (unsupported model description)') == f'{sources.root}/config/auth.php:2-2'
    with pytest.raises(ExplorationError):
        sources.validate('config/auth.php:1-3')


def test_content_search_executes_real_rg_and_records_evidence(sources):
    result = asyncio.run(sources.invoke('Grep', {'pattern': 'session', 'output_mode': 'content', '-C': 0}))
    assert f"{sources.root}/config/auth.php:3:'driver' => 'session'," in result
    assert sources.validate('config/auth.php:3') == f'{sources.root}/config/auth.php:3-3'
    with pytest.raises(ExplorationError):
        sources.validate('config/auth.php:1-3')


def test_file_discovery_is_not_source_evidence(sources):
    result = asyncio.run(sources.invoke('Glob', {'pattern': '**/auth.php'}))
    assert result == f'{sources.root}/config/auth.php'
    result = asyncio.run(sources.invoke('Grep', {'pattern': 'session'}))
    assert result == f'{sources.root}/config/auth.php'
    with pytest.raises(ExplorationError):
        sources.validate('config/auth.php:1-3')


@pytest.mark.parametrize('name,args', [
    ('Read', {'path': '/invented-workspace/config/auth.php'}),
    ('Glob', {'directory': '/invented-workspace', 'pattern': '**/auth.php'}),
    ('Grep', {'path': '/invented-workspace', 'pattern': 'auth'}),
    ('Read', {'path': '../outside.php'}),
])
def test_scope_escape_and_invented_prefixes_are_rejected(sources, name, args):
    with pytest.raises(ValueError, match='outside the repository'):
        asyncio.run(sources.invoke(name, args))


def test_symlink_escape_is_rejected(sources, tmp_path):
    outside = tmp_path.parent / 'outside-source.php'
    outside.write_text('private')
    (sources.root / 'escape.php').symlink_to(outside)
    with pytest.raises(ValueError, match='outside the repository'):
        asyncio.run(sources.invoke('Read', {'path': 'escape.php'}))


def test_changed_source_and_nonexistent_citations_cannot_pass(sources):
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php'}))
    (sources.root / 'config/auth.php').write_text('changed\n')
    with pytest.raises(ExplorationError):
        sources.validate('config/auth.php:1')
    with pytest.raises(ValueError):
        sources.validate('missing.php:1')
    with pytest.raises(ValueError):
        sources.validate('config:1')


def test_answer_prose_is_not_forwarded_and_every_citation_must_validate(sources):
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php'}))
    assert sources.validate('Invented explanation\n<final_answer>config/auth.php:1-3 (invented claim)</final_answer>') == f'{sources.root}/config/auth.php:1-3'
    with pytest.raises(ValueError):
        sources.validate('<final_answer>config/auth.php:1-3\nmissing.php:1-10</final_answer>')
    with pytest.raises(ExplorationError):
        sources.validate('I found nothing but here is a confident unsupported answer.')


def test_tool_errors_are_returned_with_actual_root(sources):
    call = SimpleNamespace(name='Read', arguments=json.dumps({'path': '/wrong/auth.php'}), id='call_1')
    results = asyncio.run(sources.call(SimpleNamespace(tool_calls=[call])))
    assert results[0].content.startswith('Tool error:')
    assert str(sources.root) in results[0].content
    assert not sources.evidence


def test_orientation_uses_real_paths_and_does_not_count_as_reading(sources):
    prompt = asyncio.run(sources.orient('Find auth configuration'))
    assert f'{sources.root}/config/auth.php' in prompt
    assert '<query>Find auth configuration</query>' in prompt
    assert not sources.evidence


def test_receipts_never_fill_unread_gaps(sources):
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php', 'offset': 1, 'limit': 1}))
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php', 'offset': 3, 'limit': 1}))
    assert sources.receipts().splitlines() == [f'{sources.root}/config/auth.php:1-1', f'{sources.root}/config/auth.php:3-3']
    with pytest.raises(ExplorationError):
        sources.validate('config/auth.php:1-3')


def test_repeated_reads_do_not_duplicate_source_in_model_context(sources):
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php'}))
    repeated = asyncio.run(sources.invoke('Read', {'path': 'config/auth.php'}))
    assert repeated.startswith('Already read ')
    assert "'driver' => 'session'" not in repeated
    assert sources.validate('config/auth.php:1-3') == f'{sources.root}/config/auth.php:1-3'


def test_partial_results_drop_every_unobserved_citation(sources):
    asyncio.run(sources.invoke('Read', {'path': 'config/auth.php'}))
    mixed = '<final_answer>config/auth.php:1-3 (claim omitted)\n/invented/file.php:1-20\nconfig/auth.php:1-500\nUnsupported prose</final_answer>'
    assert sources.verified_subset(mixed) == f'{sources.root}/config/auth.php:1-3'


def test_file_orientation_does_not_let_one_directory_hide_other_layers(sources):
    for number in range(20):
        (sources.root / 'config' / f'auth{number}.php').write_text('auth')
    (sources.root / 'routes').mkdir()
    (sources.root / 'routes/auth.php').write_text('auth')
    prompt = asyncio.run(sources.orient('Find authentication configuration and routes'))
    assert str(sources.root / 'routes/auth.php') in prompt
    assert prompt.count(str(sources.root / 'config/')) <= 3
