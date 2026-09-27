from copy import deepcopy
from src.companion import initial_state, CompanionStore
from src.personal_discoveries import retain_impressions, opening_mode


def impression(**changes):
    return dict(source_id='source', detail='最後の一音を変えていた', feeling='余韻が残る終わり方が好き',
                reason='説明しすぎない余白に惹かれる', want_to_try='音の重なりにも注目したい',
                relation='new', previous_id='', change_reason='', **changes)


def test_evidence_and_continuity_required():
    s = initial_state()
    batch = {**deepcopy(s), 'findings':[{'id':'source', 'sources':[{'title':'資料','url':'https://example.org'}]}]}
    bad = impression(); bad['source_id']='invented'
    retain_impressions(s, {'personal_impressions':[bad]}, batch, 1)
    assert not s['personal_impressions']
    bad = impression(); bad.update(relation='changed', previous_id='imaginary', change_reason='変わった')
    retain_impressions(s, {'personal_impressions':[bad]}, batch, 1)
    assert not s['personal_impressions']
    retain_impressions(s, {'personal_impressions':[impression()]}, batch, 2)
    first = s['personal_impressions'][0]
    assert first['sources'][0]['url']=='https://example.org'
    retain_impressions(s, {'personal_impressions':[impression()]}, batch, 3)
    assert len(s['personal_impressions'])==1
    batch = deepcopy(s); batch['findings']=[{'id':'next', 'sources':first['sources']}]
    changed = impression(); changed.update(source_id='next', relation='deepened', previous_id=first['id'], change_reason='終わりだけでなく途中の間にも惹かれた')
    retain_impressions(s, {'personal_impressions':[changed]}, batch, 4)
    assert s['personal_impressions'][-1]['previous_feeling']==first['feeling']


def test_openings_do_not_chain_questions_or_invent_callbacks():
    assert opening_mode({})=='thought'
    assert opening_mode({'recent_noah_messages':[{'text':'音の余白が好き。どう思う？'}]})=='thought'
    assert opening_mode({'recent_noah_messages':[{'text':'音の余白が好き。'}]})=='invitation'
    records={'recent_noah_messages':[{'text':'a'},{'text':'b'}]}
    assert opening_mode(records)!='callback'
    records['shared_memories']=['一緒に音の話をした']
    assert opening_mode(records)=='callback'


def test_existing_state_can_load_and_impressions_reach_chat(tmp_path):
    store=CompanionStore(tmp_path/'s.json')
    store.change(lambda s:s.update(personal_impressions=[{'feeling':'余白が好き'}]))
    context,_=store.context(query='何が好き')
    assert '余白が好き' in context


def test_thought_mode_removes_unpunctuated_prompt_for_reply():
    from src.initiative.generation import _sanitize_generated_text
    assert _sanitize_generated_text('音の余白が好き。どんな音が好きなのかな。') == '音の余白が好き。'


def test_no_new_sources_avoids_another_api_call():
    from src.personal_discoveries import reflect_discoveries
    from unittest.mock import Mock
    client = Mock()
    assert reflect_discoveries(client, {'findings':[], 'video_observations':[]}) == []
    client.responses.create.assert_not_called()
