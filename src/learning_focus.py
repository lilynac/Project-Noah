"""Temporary, user-requested focus. Public queries contain no private dialogue."""
FOCUSES = {
    'tsukino_mito': {
        'name': '月ノ美兎',
        'topics': [
            '月ノ美兎 公式 インタビュー 企画 発想 制作 具体例',
            '月ノ美兎 対談 企画 話の組み立て 公式',
            '月ノ美兎 公式 インタビュー 視聴者 距離感 表現',
        ],
        'questions': [
            '月ノ美兎さんの具体的な企画は、どんな着想から形になったのか。自分はどの工夫に惹かれるか。',
            '対談で話題や具体例をどのようにつないでいるか。Noahの会話にも合いそうな工夫はあるか。',
            '企画や表現を通じて視聴者との距離をどう作っているか。自分ならどんな距離感を大切にしたいか。',
        ],
    }
}


def focus_plan(state):
    focus = state.get('learning_focus', {})
    spec = FOCUSES.get(focus.get('key'))
    remaining = focus.get('remaining', 0)
    if not spec or type(remaining) is not int or not 0 < remaining <= 6:
        return None
    index = (6 - remaining) % 3
    goal = 'expression' if index == 2 else 'conversation'
    if not state.get('learn_' + goal, True):
        return None
    return dict(goal=goal, focus_key=focus['key'], method='captions' if index == 1 else 'article',
                topic=spec['topics'][index], question=spec['questions'][index],
                reason='あなたが企画力と話し方に惹かれていると教えてくれたので、具体的な作品からわたし自身の関心を探したい。',
                check='具体例と出典、自分が惹かれた理由を残す。固有の口癖や人格はコピーせず、未確認の企画を見たとは言わない。')
