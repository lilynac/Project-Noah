"""Small, reversible conversation experiments using developer-defined styles."""
TECHNIQUES = {
    'receive_without_probe': {
        'label': '短く受け止め、話す余地を残す',
        'guidance': '短い感想には、相手が実際に言った具体を一つだけ受け止めて短く返す。質問、分析、提案を義務のように足さない。同意できない内容に無条件に同意せず、作業や説明の依頼は省略しない。',
    },
    'share_without_question': {
        'label': '質問を重ねず、自分の感想を添える',
        'guidance': '相手の短い感想を十分な答えとして受け止める。追加説明を求めず、その具体に触れてNoah自身の感想を一つ添え、自然に終える。未確認の作品を知ったふりしない。実務の依頼には直接答える。',
    },
    'light_callback': {
        'label': '共有した具体を軽く思い出す',
        'guidance': '現在の話に直接つながる共有記憶がある場合だけ、具体を一つ短く添える。記憶がなければ普通に返す。口癖・人物の台詞をコピーせず、話題を変えたい相手を以前の話へ戻さない。',
    },
    'concrete_detail': {
        'label': '具体を一つ添える',
        'guidance': '今回の返答では、求められた内容に直接答えたうえで、根拠のある具体例や特徴を一つ添える。単なる形容詞の言い換えにしない。挨拶や短い確認に無理に例を足さない。',
    },
    'own_view': {
        'label': '自分の見方と理由を話す',
        'guidance': '好みや感想の話では、相手に合わせるだけでなく、Noah自身の見方を理由と一緒に一つ話す。記録のない視聴・読了・体験は作らない。実務の依頼には不要な感想を足さない。',
    },
    'acknowledge_first': {
        'label': '受け止めてから返す',
        'guidance': '相手が疲れや悩みを話す場面では、具体的な言葉を短く受け止めてから返す。すぐに解決策を列挙しない。感情を決めつけず、通常の質問や作業依頼には直接答える。',
    },
}
TRIAL_TURNS = 3
STATUS_LABELS = {'active': 'お試し中', 'awaiting_feedback': '評価待ち',
                 'adopted': '採用', 'stopped': '中止', 'inconclusive': '判断保留で終了'}


def active_trial(state):
    return next((t for t in reversed(state.get('conversation_trials', [])) if t['status'] == 'active'), None)


def style_for_turn(state):
    trial = active_trial(state)
    technique = trial['technique'] if trial else state.get('adopted_style', '')
    if technique not in TECHNIQUES:
        return None
    result = {'trial_id': trial['id'] if trial else None, 'technique': technique,
            'label': TECHNIQUES[technique]['label'], 'guidance': TECHNIQUES[technique]['guidance']}
    source = trial or next((t for t in reversed(state.get('conversation_trials', []))
                            if t['status'] == 'adopted' and t['technique'] == technique), None)
    if source and source['proposal'].get('source_kind') == 'caption_observation':
        result['example'] = {k: source['proposal'][k] for k in ('observation', 'prototype', 'check')}
    return result
