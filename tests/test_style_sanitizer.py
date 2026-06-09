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
