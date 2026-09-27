"""Purpose-led learning; material types are tools, never personality goals."""
GOALS = {'conversation': '自然に会話するには', 'expression': '自分らしく振る舞うには'}
METHODS = {'captions': '公開対談の字幕を読む', 'article': '公開記事・制作記録を読む', 'frames': '表情の描かれ方を静止画で観察する'}
TOPICS = {'conversation': '対談 インタビュー 聞き手 自分の感想 質問しすぎない 会話 工夫',
          'expression': 'キャラクター 表情 視線 個性 表現 制作 インタビュー'}


def valid_direction(value):
    if not isinstance(value, dict) or value.get('goal') not in GOALS or value.get('method') not in ('article', 'captions'):
        return False
    placeholders = {'具体的な問い', '記録に基づく理由', '確かめ方', '確認方法', '選ぶ理由', '...'}
    return all(isinstance(value.get(k), str) and 8 <= len(value[k].strip()) <= 250
               and value[k].strip() not in placeholders for k in ('question', 'reason', 'check'))


def choose_plan(state):
    enabled = [g for g in GOALS if state.get('learn_' + g, True)]
    if not state.get('video_learning_enabled') or not enabled:
        return {}
    from .learning_focus import focus_plan
    focused = focus_plan(state)
    if focused:
        return focused
    history = state.get('learning_history', [])
    counts = {g: sum(p['goal'] == g for p in history) for g in enabled}
    suggestion = state.get('learning_direction', {})
    if not valid_direction(suggestion):
        suggestion = {}
    goal = suggestion.get('goal')
    if goal not in enabled:
        goal = min(enabled, key=lambda g: counts[g])
    previous = [p for p in history if p['goal'] == goal]
    if goal == 'conversation':
        method = 'captions' if len(previous) % 2 == 0 else 'article'
        question = '質問を重ねず、自分の感想も添えて会話を続けるには？'
        check = '返し方を小さく試し、ユーザーの明示的な感想で見直す。'
    else:
        available = state.get('video_visual_enabled') and any(not n.get('visual_status') for n in state.get('video_observations', []))
        method = 'frames' if available else 'article'
        question = '自分の気持ちが伝わる表情や見せ方には、どんな工夫がある？'
        check = 'Noahに合う表現案と理由を残す。実装済みとは扱わない。'
    if suggestion.get('goal') == goal and suggestion.get('method') in ('article', 'captions'):
        method = suggestion['method'] if goal == 'conversation' else 'article'
    reason = '最近の会話と調査の偏りを振り返り、この目的を確かめたい。'
    if goal == 'conversation' and state.get('video_preferences'):
        reason = 'あなたが伝えてくれた会話の好みを、実際の返し方に生かしたい。'
    plan = {'goal': goal, 'question': question, 'reason': reason, 'method': method,
            'topic': TOPICS[goal], 'check': check}
    if suggestion.get('goal') == goal:
        for key in ('question', 'reason', 'check'):
            if suggestion.get(key):
                plan[key] = suggestion[key]
    return plan


def run_plan(store, client, batch, now, cancelled=lambda: False):
    plan = choose_plan(batch)
    if not plan or cancelled():
        return
    def stopped():
        current = store.snapshot()
        return cancelled() or not current['video_learning_enabled'] or not current.get('learn_' + plan['goal'], True)
    store.change(lambda s: s.update(learning_plan={**plan, 'status': '調査中'}, learning_direction={}))
    before = store.snapshot()
    if stopped():
        store.change(lambda s: s.update(learning_plan={**plan, 'status': '中断'}))
        return
    status = '根拠を得られず。次の計画で資料や方法を見直す。'
    try:
        if plan['method'] == 'article':
            from .companion_life import research
            from .companion import research_history
            summary, sources = research(client, plan['topic'], research_history(batch, plan['topic']))
            if not stopped():
                store.save_finding(plan['topic'], summary, sources, now())
                status = '調査メモを保存。振り返りで具体的な工夫を検討する。'
        elif plan['method'] == 'captions':
            from .video_learning import run_research
            run_research(store, client, batch, now, stopped)
            if {n['id'] for n in store.snapshot()['video_observations']} - {n['id'] for n in before['video_observations']}:
                status = '会話の観察を保存。根拠のある工夫を小さく試す。'
        else:
            from .video_vision import run_visual_research
            run_visual_research(store, client, now, stopped)
            if store.snapshot()['video_observations'] != before['video_observations']:
                status = '静止画の確認結果を記録。表現案は未実装。'
        if stopped():
            status = '中断。確認済みの記録だけを保持。'
    except Exception:
        status = '調査に失敗。次の予定で方法を見直す。'
    record = {**plan, 'status': status, 'at': now()}
    def finish(s):
        focus = s.get('learning_focus', {})
        if plan.get('focus_key') and focus.get('key') == plan['focus_key']:
            focus['remaining'] = max(0, focus.get('remaining', 0) - 1)
        s['learning_history'] = (s['learning_history'] + [record])[-30:]
        s['learning_plan'] = record
    store.change(finish)
