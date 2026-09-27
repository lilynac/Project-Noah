from datetime import datetime
from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.companion import CompanionStore
from src.initiative.runner import initiative_loop


class OneTick:
    def __init__(self):
        self.waits = 0

    def is_set(self):
        return False

    def wait(self, delay):
        self.waits += 1
        return self.waits > 1


def runtime(store, now):
    client = Mock()
    client.with_options.return_value.responses.create.return_value = SimpleNamespace(
        status='completed', output_text='{"concrete":true,"grounded":true,"honest":true,"novel":true}')
    return {
        'companion': store,
        '_get_logger': Mock(), 'random': SimpleNamespace(uniform=lambda *args: 0),
        'time': SimpleNamespace(time=lambda: now), '_next_initiative_delay': lambda: 1,
        'DEBUG_INITIATIVE_LOOP': False, 'is_work_mode': lambda: False,
        'should_fire_initiative': Mock(return_value=(True, 'ready')),
        '_recent_turn_texts': lambda: ['星の話'], 'load_state_snippet': lambda: '',
        'DecisionEngine': None, 'load_signals': None, 'set_initiative_state': Mock(),
        '_state_lock': Lock(), '_initiative_count': 0, 'client': client,
        'generate_initiative_text': Mock(return_value=SimpleNamespace(text='星の色の違いが気になるよ。', reasons=['llm_generated'])),
        '_initiative_is_duplicate': lambda value: False,
        'emit_initiative': Mock(return_value=True),
        'touch_noah_message': None, 'save_signals': None,
        'log_error': Mock(), '_last_noah_initiative_at': 0,
    }


def test_scheduled_finding_reaches_chat_outbox_with_sources(tmp_path):
    now = datetime(2026, 9, 23, 12).timestamp()
    store = CompanionStore(tmp_path / 'companion.json')
    store.seed([], now)
    store.change(lambda state: state.update(next_talk_at=now))
    store.save_finding('星', '星の色と温度。', [{'title': '資料', 'url': 'https://example.org'}], now)
    env = runtime(store, now)
    initiative_loop(OneTick(), env)
    env['log_error'].assert_not_called()
    env['emit_initiative'].assert_called_once()
    assert 'https://example.org' in env['emit_initiative'].call_args.args[0]
    assert store.snapshot()['findings'][0]['shared']
    assert len(store.snapshot()['outbox']) == 1


@pytest.mark.parametrize('block', ['work', 'ipc_busy', 'pause', 'future', 'quiet'])
def test_scheduler_never_generates_while_blocked(tmp_path, block):
    now = datetime(2026, 9, 23, 12).timestamp()
    store = CompanionStore(tmp_path / 'companion.json')
    store.seed([], now)
    store.change(lambda state: state.update(next_talk_at=now))
    env = runtime(store, now)
    if block == 'work':
        env['is_work_mode'] = lambda: True
    elif block == 'ipc_busy':
        env['should_fire_initiative'].return_value = False, 'ipc_busy'
    elif block == 'pause':
        store.set_enabled('talk_enabled', False)
    elif block == 'future':
        store.change(lambda state: state.update(next_talk_at=now + 3600))
    elif block == 'quiet':
        env['time'].time = lambda: datetime(2026, 9, 24, 2).timestamp()
    initiative_loop(OneTick(), env)
    env['generate_initiative_text'].assert_not_called()
    env['emit_initiative'].assert_not_called()
    env['log_error'].assert_not_called()


def test_failed_generation_is_delayed_without_marking_finding_shared(tmp_path):
    now = datetime(2026, 9, 23, 12).timestamp()
    store = CompanionStore(tmp_path / 'companion.json')
    store.seed([], now)
    store.change(lambda state: state.update(next_talk_at=now))
    store.save_finding('星', '星の色。', [{'title': '資料', 'url': 'https://example.org'}], now)
    env = runtime(store, now)
    env['generate_initiative_text'].return_value = SimpleNamespace(text='定型句', reasons=['fallback'])
    initiative_loop(OneTick(), env)
    env['emit_initiative'].assert_not_called()
    assert not store.snapshot()['findings'][0]['shared']
    assert store.snapshot()['next_talk_at'] == now + 3600


def test_question_removal_keeps_complete_observation():
    from src.initiative.generation import _sanitize_generated_text
    assert _sanitize_generated_text('動きを逆算する工夫が気になったよ。あなたはどう思う？') == '動きを逆算する工夫が気になったよ。'
    assert _sanitize_generated_text('どう思う？') == ''


def test_clip_drops_unfinished_trailing_sentence():
    from src.initiative.generation import _clip
    assert _clip('具体的な発見。' + '続き' * 80, 30) == '具体的な発見。'


@pytest.mark.parametrize('failure', ['honest', 'concrete', 'novel', 'grounded', 'timeout'])
def test_quality_rejection_preserves_finding_and_delays_without_quota(tmp_path, failure):
    import json
    now = datetime(2026, 9, 23, 12).timestamp()
    store = CompanionStore(tmp_path / 'companion.json')
    store.seed([], now)
    store.change(lambda s: s.update(next_talk_at=now))
    store.save_finding('星', '星の色と温度。', [{'title': '資料', 'url': 'https://example.org'}], now)
    env = runtime(store, now)
    api = env['client'].with_options.return_value.responses.create
    if failure == 'timeout':
        api.side_effect = TimeoutError()
    else:
        flags = dict(concrete=True, grounded=True, honest=True, novel=True)
        flags[failure] = False
        api.return_value.output_text = json.dumps(flags)
    initiative_loop(OneTick(), env)
    env['emit_initiative'].assert_not_called()
    env['generate_initiative_text'].assert_called_once()
    saved = store.snapshot()
    assert saved['daily']['talk'] == 0
    assert saved['outbox'] == []
    assert not saved['findings'][0]['shared']
    assert saved['next_talk_at'] == now + 3600
    assert saved['last_quality']['reason'] == ('unavailable' if failure == 'timeout' else failure)


def test_invitation_after_specific_thought_survives():
    from src.initiative.generation import _sanitize_generated_text
    assert _sanitize_generated_text('この音の重ね方が好き。こんな話する？', allow_invitation=True) == 'この音の重ね方が好き。こんな話する？'
    assert _sanitize_generated_text('どう思う？', allow_invitation=True) == ''
    assert _sanitize_generated_text('この工夫が好き。どう思う？なぜ？', allow_invitation=True).count('？') == 1


def test_unshared_caption_becomes_topic_and_is_marked_delivered(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    store.change(lambda s:s.update(video_observations=[dict(id='note', title='制作の対談', url='https://www.youtube.com/watch?v=abcdefghijk', at=50, at_seconds=10, observation='音の重ね方を工夫している', access='字幕のみ')]))
    context, finding = store.context(initiative=True)
    assert finding['id'] == 'note' and '&t=10' in finding['sources'][0]['url']
    store.delivered('この音の工夫が気になった。', finding['id'], now=100)
    assert store.context(initiative=True)[1] is None
