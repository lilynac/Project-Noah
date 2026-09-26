from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.companion import CompanionStore, planned_time
from src.companion_life import CompanionLife, research, start_companion


@pytest.fixture(autouse=True)
def offline_reader(monkeypatch):
    monkeypatch.setattr("src.companion_life.read_public_page", lambda url: None)


@pytest.fixture
def now():
    return datetime(2026, 9, 23, 12).timestamp()


@pytest.fixture
def store(tmp_path):
    return CompanionStore(tmp_path / 'companion.json')


def prepare(store, now):
    store.seed([], now)
    store.record_turn('星を見るのが好き。', '星の色の違いも気になるね。', now)
    return store.snapshot()


def reflection(event_id):
    return {
        'memories': [{'text': '星を見るのが好きと話してくれた。', 'evidence_id': event_id}],
        'preferences': [{'text': '星の色の違いに惹かれる。', 'evidence_id': event_id}],
        'interests': [{'topic': '恒星の色', 'origin': 'noah', 'reason': '色と温度の関係を知りたい。'}],
        'research_topic': '恒星の色', 'research_in_minutes': 180,
        'talk_in_minutes': 240, 'plan_reason': '夕方に、星の話の続きを少し。',
    }


def test_seed_and_turns_survive_restart_without_passive_growth(store, now):
    history = [{'role': 'user', 'content': 'おかえり'}, {'role': 'assistant', 'content': 'ただいま。'}]
    store.seed(history, now)
    original = store.snapshot()
    restarted = CompanionStore(store.path)
    restarted.seed(history, now + 86400)
    assert restarted.snapshot() == original
    assert len(original['pending']) == 1
    assert original['affection'] == .25
    restarted.record_turn('ありがとう', 'うれしい。', now + 86400)
    assert restarted.snapshot()['affection'] > original['affection']


def test_parallel_turns_are_not_lost(store, now):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: store.record_turn(str(n), '返事', now), range(40)))
    state = store.snapshot()
    assert state['turn_count'] == 40
    assert len(state['pending']) == 40
    assert len({item['id'] for item in state['pending']}) == 40


def test_reflection_requires_evidence_and_preserves_new_turns(store, now):
    batch = prepare(store, now)
    result = reflection(batch['pending'][0]['id'])
    result['memories'].append({'text': '架空の旅行', 'evidence_id': 'invented'})
    store.record_turn('新しい話', '続きを聞いてる。', now + 2)
    store.apply_reflection(result, batch, now + 10)
    state = store.snapshot()
    assert len(state['memories']) == 1
    assert state['preferences'][0]['evidence']['user'] == '星を見るのが好き。'
    assert [item['user'] for item in state['pending']] == ['新しい話']
    assert state['next_talk_at'] == now + 10 + 90 * 60
    assert state['research_topic'] == '恒星の色'


def test_invalid_reflection_is_transactional(store, now):
    batch = prepare(store, now)
    result = reflection(batch['pending'][0]['id'])
    result['interests'] = 'wrong shape'
    before = store.snapshot()
    with pytest.raises(ValueError):
        store.apply_reflection(result, batch, now)
    assert store.snapshot() == before


def test_empty_json_response_keeps_experiences_for_retry(store, now):
    batch = prepare(store, now)
    with pytest.raises(ValueError):
        store.apply_reflection({}, batch, now)
    assert store.snapshot()['pending'] == batch['pending']


def test_existing_relationship_is_imported_once(store, now):
    store.seed([], now, relationship={'affection': .7, 'trust': .6})
    store.seed([], now + 10, relationship={'affection': .1, 'trust': .1})
    assert store.snapshot()['affection'] == .7


def test_no_new_experience_does_not_rewrite_state(store, now, monkeypatch):
    store.seed([], now)
    store.change(lambda state: state['daily'].update(day=datetime.fromtimestamp(now).date().isoformat()))
    write = Mock()
    monkeypatch.setattr(store, '_write', write)
    assert store.claim('reflection', now + 3600) is None
    write.assert_not_called()


def test_restart_and_failures_do_not_reset_daily_request_limit(store, now):
    prepare(store, now)
    store.change(lambda state: state.update(research_topic='星', next_research_at=now))
    assert store.claim('research', now)
    restarted = CompanionStore(store.path)
    assert restarted.claim('research', now + 30) is None
    assert restarted.claim('research', now + 6 * 3600)
    restarted.change(lambda state: state.update(next_research_at=now + 7 * 3600))
    assert restarted.claim('research', now + 7 * 3600) is None
    tomorrow = (datetime.fromtimestamp(now) + timedelta(days=1)).timestamp()
    assert restarted.claim('research', tomorrow)


def test_schedule_clamps_model_times_and_avoids_quiet_hours(now):
    assert planned_time(now, -200) == now + 30 * 60
    assert planned_time(now, 999999) == now + 86400
    assert planned_time(now, float('nan')) == now + 120 * 60
    assert datetime.fromtimestamp(planned_time(datetime(2026, 9, 23, 23, 50).timestamp(), 30)).hour == 8


def test_pauses_and_talk_daily_limit_persist(store, now):
    prepare(store, now)
    store.change(lambda state: state.update(next_talk_at=now))
    assert store.talk_due(now)
    store.set_enabled('talk_enabled', False)
    assert not CompanionStore(store.path).talk_due(now)
    store.set_enabled('talk_enabled', True)
    for i in range(8):
        store.delivered('声かけ', now=now + i * 3600)
        store.change(lambda state: state.update(next_talk_at=now))
    assert not store.talk_due(now + 8 * 3600)
    store.set_enabled('research_enabled', False)
    store.change(lambda state: state.update(research_topic='星'))
    assert store.claim('research', now) is None


def test_corrupt_file_is_preserved(store):
    store.path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        store.record_turn('hello', 'reply')
    assert store.path.read_text(encoding='utf-8') == '{broken'


def test_failed_atomic_replace_keeps_previous_state(store, now, monkeypatch):
    prepare(store, now)
    before = store.path.read_text(encoding='utf-8')
    monkeypatch.setattr('src.companion.os.replace', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        store.record_turn('new', 'reply', now)
    assert store.path.read_text(encoding='utf-8') == before


def api_response(*, cited=True, searched=True):
    annotation = SimpleNamespace(type='url_citation', title='星の色', url='https://example.org/stars')
    output = [SimpleNamespace(type='message', content=[SimpleNamespace(annotations=[annotation] if cited else [])])]
    if searched:
        output.insert(0, SimpleNamespace(type='web_search_call', status='completed'))
    return SimpleNamespace(status='completed', output_text='星の色と表面温度は関係する。', output=output)


@pytest.mark.parametrize('cited,searched', [(False, True), (True, False)])
def test_search_requires_completed_tool_and_real_annotations(cited, searched):
    client = Mock()
    client.responses.create.return_value = api_response(cited=cited, searched=searched)
    with pytest.raises(ValueError):
        research(client, '星')


def test_web_research_sends_only_topic_and_preserves_sources():
    client = Mock()
    client.responses.create.return_value = api_response()
    summary, sources = research(client, '恒星の色')
    args = client.responses.create.call_args.kwargs
    assert args['tool_choice'] == 'required'
    assert json.loads(args['input'][1]['content']) == {'topic': '恒星の色'}
    assert sources == [{'title': '星の色', 'url': 'https://example.org/stars'}]
    assert '表面温度' in summary


def test_worker_reflects_then_researches_with_bounded_requests(store, now, monkeypatch):
    batch = prepare(store, now)
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(reflection(batch['pending'][0]['id'])))
    clock = [now + 1800]
    life = CompanionLife(store, client, clock=lambda: clock[0])
    life.tick()
    assert store.snapshot()['memories']
    clock[0] += 3 * 3600
    client.responses.create.return_value = api_response()
    life.tick()
    finding = store.snapshot()['findings'][0]
    assert finding['sources'][0]['url'] == 'https://example.org/stars'
    assert not finding['shared']
    assert client.responses.create.call_count == 2
    assert store.claim('research', clock[0]) is None


def test_worker_failure_does_not_make_fake_finding_or_retry_immediately(store, now):
    prepare(store, now)
    store.change(lambda state: state.update(pending=[], research_topic='星', next_research_at=now))
    client = Mock()
    client.responses.create.side_effect = OSError('offline')
    life = CompanionLife(store, client, clock=lambda: now)
    life.tick()
    life.tick()
    assert client.responses.create.call_count == 1
    assert store.snapshot()['findings'] == []
    assert store.snapshot()['last_error']


def test_worker_respects_busy_shutdown_and_quiet_time(store, now):
    prepare(store, now)
    client = Mock()
    life = CompanionLife(store, client, busy=lambda: True, clock=lambda: now + 3600)
    life.tick()
    life.busy = lambda: False
    stopped = Event()
    stopped.set()
    life.tick(stopped)
    life.clock = lambda: datetime(2026, 9, 24, 2).timestamp()
    life.tick()
    client.responses.create.assert_not_called()


def test_context_only_uses_relevant_research_and_retains_noah_messages(store, now):
    prepare(store, now)
    store.save_finding('恒星の色', '色と温度の関係。', [{'title': '星', 'url': 'https://example.org'}], now)
    assert store.context(query='こんにちは')[1] is None
    assert store.context(query='何を調べたの')[1]
    context, finding = store.context(initiative=True)
    store.delivered('色の違いが気になって。', finding['id'], now)
    assert store.context(initiative=True)[1] is None
    assert store.snapshot()['outbox'][0]['text'] == '色の違いが気になって。'


def test_gui_service_worker_is_stoppable_without_loading_noah(store, now):
    noah = SimpleNamespace(companion=store, _conversation_lock=Lock(), CONVERSATION_HISTORY=[], client=None)
    stop = Event()
    thread = start_companion(noah, stop)
    stop.set()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert store.snapshot()['seeded']


def test_context_recalls_older_relevant_memory_with_original_words(store, now):
    old = {'text': '万年筆の青いインクを気に入っていた。', 'at': now,
           'evidence': {'user': '万年筆には青いインクを使うのが好き。'}}
    recent = [{'text': f'最近の別の出来事その{i}。', 'at': now + i + 1,
               'evidence': {'user': '別の話。'}} for i in range(10)]
    store.change(lambda state: state.update(memories=[old, *recent]))
    before = store.snapshot()
    context, finding = store.context(query='万年筆の話の続き。')
    payload = json.loads(context)
    assert old['text'] in payload['shared_memories']
    assert len(payload['shared_memories']) == 8
    assert payload['memory_details'][0]['user_words'] == old['evidence']['user']
    assert payload['memory_details'][0]['recorded_at'] == now
    assert finding is None
    assert store.snapshot() == before


def test_memory_selection_falls_back_to_recent_and_normalizes_width():
    from src.companion import select_memories
    memories = [{'text': '好きなものはＪＡＺＺ。'}, {'text': '今日の話。'}]
    assert select_memories(memories, '', limit=1) == memories[-1:]
    assert select_memories(memories, 'jazz', limit=1) == memories[:1]
    assert select_memories([], 'jazz') == []


def test_lively_pace_migrates_once_without_enabling_paused_talk(store, now):
    store.change(lambda state: state.update(
        seeded=True, next_talk_at=now + 4 * 3600, talk_enabled=False))
    store.seed([], now)
    assert store.snapshot()['next_talk_at'] == now + 45 * 60
    assert not store.snapshot()['talk_enabled']
    store.change(lambda state: state.update(next_talk_at=now + 90 * 60))
    CompanionStore(store.path).seed([], now + 60)
    assert store.snapshot()['next_talk_at'] == now + 90 * 60


def test_lively_pace_delivery_waits_45_minutes_and_respects_night(store, now):
    store.delivered('話の続き。', now=now)
    assert not store.talk_due(now + 44 * 60)
    assert store.talk_due(now + 45 * 60)
    late = datetime(2026, 9, 23, 23, 45).timestamp()
    store.delivered('今日の発見。', now=late)
    morning = datetime(2026, 9, 24, 8).timestamp()
    assert store.snapshot()['next_talk_at'] == morning
    assert not store.talk_due(morning - 1)
    assert store.talk_due(morning)


def test_research_reads_source_text_and_separates_reading_from_search(monkeypatch):
    monkeypatch.setattr('src.companion_life.read_public_page', lambda url: '実際に取得した制作記録の本文。' * 20)
    client = Mock()
    client.responses.create.side_effect = [api_response(), SimpleNamespace(
        status='completed', output_text='事実：音の間を工夫。感想：間で印象が変わるのが気になった。')]
    summary, sources = research(client, '作品の表現')
    assert '本文抜粋を読んだメモ' in summary
    payload = json.loads(client.responses.create.call_args.kwargs['input'][1]['content'])
    assert payload['documents'][0]['excerpt'].startswith('実際に取得した')
    assert sources[0]['url'] == 'https://example.org/stars'


def test_reading_failure_preserves_search_with_explicit_limit(monkeypatch):
    monkeypatch.setattr('src.companion_life.read_public_page', lambda url: '本文。' * 100)
    client = Mock()
    client.responses.create.side_effect = [api_response(), RuntimeError('unavailable')]
    summary, sources = research(client, '星')
    assert '今回は検索結果の範囲のみ' in summary
    assert sources


def test_three_pillars_migrate_without_inventing_user_interests(store, now):
    store.change(lambda s: s.update(seeded=True, interests=[{
        'topic': '星', 'reason': '色が気になる', 'origin': 'noah', 'at': now}]))
    store.seed([], now)
    state = store.snapshot()
    assert {i['pillar'] for i in state['interests']} == {'curiosity', 'expression'}
    assert state['pillars_seeded']
    store.seed([], now + 100)
    assert store.snapshot() == state


def test_improvement_requires_real_evidence_and_survives_restart(store, now):
    batch = prepare(store, now)
    result = reflection(batch['pending'][0]['id'])
    proposal = dict(observation='返答が抽象的だった。', change='具体を一つ話す。',
                    prototype='星の色の違いが気になるよ。', check='同じ形容詞を繰り返していないか。', evidence_id='invented')
    result['improvements'] = [proposal]
    store.apply_reflection(result, batch, now)
    assert not store.snapshot()['improvements']
    proposal['evidence_id'] = batch['pending'][0]['id']
    store.apply_reflection(result, batch, now + 1)
    saved = CompanionStore(store.path).snapshot()['improvements']
    assert saved[0]['status'] == 'proposal'
    assert saved[0]['evidence']['user'] == '星を見るのが好き。'
    assert saved[0]['prototype'] == proposal['prototype']
    assert json.loads(store.context()[0])['improvement_proposals'] == saved


def test_user_pillar_requires_user_evidence(store, now):
    batch = prepare(store, now)
    result = reflection(batch['pending'][0]['id'])
    result['interests'].append(dict(topic='架空の趣味', reason='推測', origin='noah', pillar='user'))
    store.apply_reflection(result, batch, now)
    assert not any(i['topic'] == '架空の趣味' for i in store.snapshot()['interests'])
