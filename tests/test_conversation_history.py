import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from src import conversation_history as history


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'MEMORY_DIR', str(tmp_path))
    monkeypatch.setattr(history, 'CONVERSATION_HISTORY', [])
    monkeypatch.setattr(history, 'CONVERSATION_MAX_TURNS', 3)
    monkeypatch.setattr(history, '_error_logger', Mock())
    return tmp_path / history.CONVERSATION_PERSIST_FILENAME


def test_turn_survives_restart_and_preserves_shared_list(store):
    reference = history.CONVERSATION_HISTORY
    history.record_conversation_turn('  やあ  ', 'こんにちは')
    expected = [{'role': 'user', 'content': 'やあ'}, {'role': 'assistant', 'content': 'こんにちは'}]
    assert json.loads(store.read_text(encoding="utf-8")) == expected
    reference.clear()
    history.load_conversation_history()
    assert reference == expected
    assert reference is history.CONVERSATION_HISTORY


def test_history_retains_complete_recent_turns(store):
    for i in range(5):
        history.record_conversation_turn(str(i), f'reply-{i}')
    assert [m['content'] for m in history.CONVERSATION_HISTORY[::2]] == ['2', '3', '4']
    assert json.loads(store.read_text(encoding="utf-8")) == history.CONVERSATION_HISTORY


def test_parallel_saves_keep_complete_turns(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: history.record_conversation_turn(str(i), f'reply-{i}'), range(30)))
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert saved == history.CONVERSATION_HISTORY
    assert len(saved) == 6
    for i in range(0, len(saved), 2):
        assert saved[i+1]['content'] == 'reply-' + saved[i]['content']


def test_save_failure_keeps_memory_and_previous_file(store, monkeypatch):
    history.record_conversation_turn('first', 'reply')
    previous = store.read_text(encoding="utf-8")
    monkeypatch.setattr(history.os, 'replace', Mock(side_effect=OSError('disk error')))
    history.record_conversation_turn('second', 'reply2')
    assert store.read_text(encoding="utf-8") == previous
    assert history.CONVERSATION_HISTORY[-1]['content'] == 'reply2'
    history._error_logger.assert_called_once()


@pytest.mark.parametrize('user,reply', [('', 'reply'), ('hi', ' '), (None, 'reply')])
def test_invalid_turn_is_not_saved(store, user, reply):
    history.record_conversation_turn(user, reply)
    assert history.CONVERSATION_HISTORY == []
    assert not store.exists()
