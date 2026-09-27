from unittest.mock import Mock
from src.companion import CompanionStore, initial_state
from src.learning_plan import choose_plan, run_plan


def test_plans_choose_purpose_and_change_material():
    s = initial_state(); s['video_learning_enabled'] = True
    first = choose_plan(s)
    assert first['goal'] == 'conversation' and first['method'] == 'captions'
    s['learning_history'] = [first]
    second = choose_plan(s)
    assert second['goal'] == 'expression' and second['method'] == 'article'
    s['learning_history'].append(second)
    assert choose_plan(s)['method'] == 'article'
    s['learn_conversation'] = False
    s['video_visual_enabled'] = True
    s['video_observations'] = [{'id': 'sample'}]
    assert choose_plan(s)['method'] == 'frames'
    s['learn_expression'] = False
    assert choose_plan(s) == {}


def test_article_plan_stores_findings_and_history(tmp_path, monkeypatch):
    store = CompanionStore(tmp_path / 'state.json')
    store.change(lambda s: s.update(video_learning_enabled=True, learn_conversation=False))
    research = Mock(return_value=('実際に読んだ内容', [{'title':'資料','url':'https://example.org'}]))
    monkeypatch.setattr('src.companion_life.research', research)
    run_plan(store, Mock(), store.snapshot(), lambda: 100)
    s = store.snapshot()
    assert s['findings'][0]['summary'] == '実際に読んだ内容'
    assert s['learning_history'][0]['goal'] == 'expression'
    assert '調査メモを保存' in s['learning_plan']['status']


def test_disabled_or_failed_plan_never_claims_learning(tmp_path, monkeypatch):
    store = CompanionStore(tmp_path / 'state.json')
    store.change(lambda s: s.update(video_learning_enabled=True, learn_conversation=False))
    research = Mock(side_effect=RuntimeError('offline'))
    monkeypatch.setattr('src.companion_life.research', research)
    run_plan(store, Mock(), store.snapshot(), lambda: 100, lambda: True)
    research.assert_not_called()
    run_plan(store, Mock(), store.snapshot(), lambda: 100)
    assert not store.snapshot()['findings']
    assert '失敗' in store.snapshot()['learning_plan']['status']


def test_material_discovery_not_fixed_to_vtubers(monkeypatch):
    import src.video_learning as video
    import json
    from types import SimpleNamespace
    commands = []
    def run(args, **kwargs):
        commands.append(args[-1])
        return SimpleNamespace(stdout=json.dumps({'entries':[{'id':'abcdefghijk', 'title':'対談'}]}))
    monkeypatch.setattr(video.subprocess, 'run', run)
    video.discover(Mock(), [])
    assert 'VTuber' not in commands[0]


def test_journal_shows_purpose_and_method():
    from src.companion_view import journal_html
    s = initial_state(); s['video_learning_enabled'] = True
    html = journal_html(s)
    assert 'わたしの学習計画' in html and '自然に会話するには' in html
    assert '今回の方法' in html and 'VTuber' not in html
