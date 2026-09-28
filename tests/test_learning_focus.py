from src.companion import initial_state
from src.learning_plan import choose_plan
from src.learning_focus import focus_plan


def test_focus_is_temporary_and_preserves_other_goals():
    s=initial_state(); s.update(video_learning_enabled=True,learning_focus={'key':'tsukino_mito','remaining':6})
    assert choose_plan(s)['focus_key']=='tsukino_mito'
    assert choose_plan(s)['method']=='article'
    s['learning_focus']['remaining']=5
    assert choose_plan(s)['method']=='captions'
    s['learning_focus']['remaining']=4
    assert choose_plan(s)['goal']=='expression'
    s['learn_expression']=False
    assert focus_plan(s) is None
    s['learning_focus']['remaining']=0
    assert 'focus_key' not in choose_plan(s)


def test_unknown_focus_cannot_become_search_query():
    s=initial_state(); s['learning_focus']={'key':'private user data', 'remaining':6}
    assert focus_plan(s) is None


def test_named_question_retrieves_specific_research(tmp_path):
    from src.companion import CompanionStore
    store=CompanionStore(tmp_path/'s.json')
    store.save_finding('月ノ美兎 公式 インタビュー 企画 発想', '企画の具体例', [{'title':'資料','url':'https://example.org'}], 1)
    context,finding=store.context(query='月ノ美兎のどこが気になった？')
    assert finding is not None and '企画の具体例' in context


def test_failed_caption_topic_gets_one_article_retry_within_budget():
    s=initial_state(); s.update(video_learning_enabled=True,learning_focus={'key':'tsukino_mito','remaining':3,'at':10})
    failed={'goal':'conversation','focus_key':'tsukino_mito','method':'captions','outcome':'no_evidence','at':20}
    s['learning_history']=[failed]
    plan=choose_plan(s)
    assert plan['method']=='article' and plan['retry_of']==20
    s['learning_history'].append({**plan,'outcome':'failed','at':30})
    assert 'retry_of' not in choose_plan(s)
    s['learning_focus']['remaining']=0
    assert 'focus_key' not in choose_plan(s)


def test_previous_focus_failure_does_not_trigger_new_focus_retry():
    s=initial_state(); s.update(video_learning_enabled=True,learning_focus={'key':'tsukino_mito','remaining':6,'at':100})
    s['learning_history']=[{'focus_key':'tsukino_mito','method':'captions','outcome':'failed','at':50}]
    assert 'retry_of' not in choose_plan(s)
