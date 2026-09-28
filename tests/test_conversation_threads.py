import json
from src.companion import CompanionStore, initial_state
from src.conversation_threads import remember_thread, link_finding, apply_links


def test_continuation_delivered_once_then_new_finding_reopens(tmp_path):
    store=CompanionStore(tmp_path/'s.json')
    event={'id':'event','user':'音の重ね方が気になる','at':1}
    store.change(lambda s:remember_thread(s,'音の重ね方','音色の違いを知りたい',event,1))
    store.save_finding('音の重ね方','重ねる順番の工夫',[{'title':'資料','url':'https://example.org'}],2)
    store.save_finding('無関係なテーマ','他の話',[{'title':'別の資料','url':'https://example.org/other'}],3)
    context,finding=store.context(initiative=True)
    assert finding['topic']=='音の重ね方'
    assert json.loads(context)['conversation_continuation']['user_words']==event['user']
    # Preparing a message is not a delivery.
    assert not store.snapshot()['conversation_threads'][0]['delivered_ids']
    store.delivered('前の音の話、順番にも工夫があるんだね。',finding['id'],now=4)
    context,_=store.context(initiative=True)
    assert 'conversation_continuation' not in json.loads(context)
    store.save_finding('音の重ね方','今度は録音の工夫',[{'title':'次の資料','url':'https://example.org/new'}],5)
    assert 'conversation_continuation' in json.loads(store.context(initiative=True)[0])


def test_no_invented_event_or_unknown_source_link():
    state=initial_state()
    remember_thread(state,'題材','気になる',{},1)
    assert not state['conversation_threads']
    event={'id':'e','user':'企画が好き','at':1}
    remember_thread(state,'企画','作り方',event,1)
    remember_thread(state,'企画','作り方',event,2)
    assert len(state['conversation_threads'])==1
    thread=state['conversation_threads'][0]
    batch={**state,'findings':[{'id':'f'}]}
    apply_links(state,{'conversation_links':[{'thread_id':thread['id'],'finding_id':'fake','connection':'つながる具体'}]},batch)
    assert not thread['finding_ids']
    apply_links(state,{'conversation_links':[{'thread_id':thread['id'],'finding_id':'f','connection':'つながる具体'}]},batch)
    assert thread['finding_ids']==['f']


def test_identical_research_does_not_reopen_delivered_topic(tmp_path):
    store=CompanionStore(tmp_path/'s.json')
    refs=[{'title':'資料','url':'https://example.org'}]
    store.save_finding('題材','同じ内容',refs,1)
    _,first=store.context(initiative=True)
    store.delivered('この話をした',first['id'],now=2)
    store.save_finding('題材','同じ内容',refs,3)
    assert store.context(initiative=True)[1] is None
