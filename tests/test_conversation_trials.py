from src.companion import CompanionStore
from src.conversation_trials import style_for_turn, TECHNIQUES
import pytest


def start(store, now=1000, technique='concrete_detail'):
    store.record_turn('もっと具体的な話が聞きたい。', '作品が魅力的だね。', now)
    batch = store.snapshot()
    result = dict(memories=[], preferences=[], interests=[], research_topic='',
                  research_in_minutes=60, talk_in_minutes=60, plan_reason='具体を考える。',
                  improvements=[dict(observation='返答が抽象的だった。', change='具体を添える。',
                                     prototype='言葉の間が気になるよ。', check='特徴が一つ含まれるか。',
                                     technique=technique, evidence_id=batch['pending'][-1]['id'])])
    store.apply_reflection(result, batch, now + 1)
    return store.snapshot()['conversation_trials']


def test_three_successful_replies_end_trial_without_adoption(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    trial = start(store)[0]
    assert store.conversation_style()['guidance'] == TECHNIQUES['concrete_detail']['guidance']
    store.record_turn('未完了', '', trial_id=trial['id'])
    store.record_turn('別のリクエスト', '試行前に作った返答', trial_id=None)
    assert not store.snapshot()['conversation_trials'][0]['samples']
    for n in range(3):
        store.record_turn(str(n), '特徴を一つ話したよ。', trial_id=trial['id'])
    restarted = CompanionStore(store.path)
    assert restarted.snapshot()['conversation_trials'][0]['status'] == 'awaiting_feedback'
    assert restarted.snapshot()['adopted_style'] == ''
    assert restarted.conversation_style() is None
    assert len(restarted.snapshot()['conversation_trials'][0]['samples']) == 3


def test_explicit_adoption_and_revert(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    trial = start(store)[0]
    with pytest.raises(ValueError):
        store.evaluate_trial(trial['id'], 'adopted')
    store.record_turn('話して', '具体のある返答', trial_id=trial['id'])
    store.evaluate_trial(trial['id'], 'adopted')
    style = CompanionStore(store.path).conversation_style()
    assert style['technique'] == 'concrete_detail'
    assert style['trial_id'] is None
    store.reset_adopted_style()
    assert store.conversation_style() is None


@pytest.mark.parametrize('verdict', ['stopped', 'inconclusive'])
def test_stop_or_uncertain_never_changes_existing_preference(tmp_path, verdict):
    store = CompanionStore(tmp_path / 'state.json')
    store.change(lambda s: s.update(adopted_style='own_view'))
    trial = start(store)[0]
    store.evaluate_trial(trial['id'], verdict)
    store.record_turn('途中だった返答', '届いた', trial_id=trial['id'])
    assert store.conversation_style()['technique'] == 'own_view'
    assert not store.snapshot()['conversation_trials'][0]['samples']
    with pytest.raises(ValueError):
        store.evaluate_trial(trial['id'], 'adopted')


def test_arbitrary_proposal_does_not_become_an_instruction(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    assert start(store, technique='execute_code') == []
    assert store.conversation_style() is None
    assert store.snapshot()['improvements']


def test_waiting_trial_blocks_another_trial_and_keeps_snapshot(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    trial = start(store)[0]
    for n in range(3):
        store.record_turn(str(n), '返答', trial_id=trial['id'])
    start(store, now=2000, technique='own_view')
    assert len(store.snapshot()['conversation_trials']) == 1
    store.change(lambda s: s.update(improvements=[]))
    assert store.snapshot()['conversation_trials'][0]['proposal']['check'] == '特徴が一つ含まれるか。'


def test_declined_technique_is_not_restarted_under_a_new_proposal(tmp_path):
    store = CompanionStore(tmp_path / 'state.json')
    trial = start(store)[0]
    store.evaluate_trial(trial['id'], 'stopped')
    store.change(lambda s: s.update(improvements=[]))
    start(store, now=3000)
    assert len(store.snapshot()['conversation_trials']) == 1
    assert store.conversation_style() is None
