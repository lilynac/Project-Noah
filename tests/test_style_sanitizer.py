from src.reply_sanitizer import sanitize_reply_style


def test_greeting_does_not_keep_quiet_night_closing():
    assert sanitize_reply_style("こんばんは", "こんばんは。静かな夜だね。") == "こんばんは。今日も来てくれてうれしいよ。"


def test_story_trims_final_atmosphere_sentence():
    reply = "昔々、若者が村を助けた。静かな夜、星空の下で彼は微笑んだ。"
    assert sanitize_reply_style("昔話をして。", reply) == "昔々、若者が村を助けた。"


def test_check_context_gets_concrete_fallback_when_vague():
    reply = "その気持ち、わかるよ。実際の会話は大切な体験だね。心に残る瞬間が生まれることもある。"
    out = sanitize_reply_style("次は実際の会話で確認したい。", reply)
    assert "確認" in out
    assert "心に残る" not in out


def test_trims_repeated_probing_but_keeps_substantive_answer():
    assert sanitize_reply_style('絵作りかな', '絵の印象が残ったんだね。どんなシーンが特に気に入ったのかな。') == '絵の印象が残ったんだね。'
    assert sanitize_reply_style('昔の感じ', '色の重ね方を想像したよ。どの部分が共通していると感じたのかな。') == '色の重ね方を想像したよ。'


def test_preserves_requested_or_quoted_questions():
    text = '一つずつ聞くね。どんな場面が好きなのかな。'
    assert sanitize_reply_style('質問して', text) == text
    quoted = '彼女は「どんな場面が好きなのかな」と尋ねた。'
    assert sanitize_reply_style('続けて', quoted) == quoted
    question = 'どんな場面が好きなのかな。'
    assert sanitize_reply_style('作品の話', question) == question


def test_trims_disguised_question_invitation():
    assert sanitize_reply_style('知っている？', '確かな知識はないな。もし感想があれば、ぜひ聞かせてほしい。') == '確かな知識はないな。'
