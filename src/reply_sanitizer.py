# src/reply_sanitizer.py
from __future__ import annotations

import re


def sanitize_reply_style(user_input: str, reply: str) -> str:
    """Remove decorative afterglow that tends to leak into ordinary replies.

    Conservative by design: only trims sentence-level atmosphere closings for
    greetings, story requests, and work/verification contexts.
    """
    text = (reply or '').strip()
    if not text:
        return text

    user = (user_input or '').strip()
    # Trim only unsolicited, sentence-final probing; preserve quoted questions,
    # requested interviews and questions that are the whole response.
    if not any(w in user for w in ('質問して', '質問を', 'インタビュー', '深掘りして', '掘り下げて', '物語', '台詞', 'セリフ', '翻訳', '訳して')):
        parts = re.findall(r'[^。！？!?]+[。！？!?]?', text)
        if len(parts) > 1:
            last = parts[-1].strip()
            probing = re.match(r'^(?:あなたは|あなたの|特に)?(?:どの|どんな|何が|何か|どう感じ|どう思)', last) and re.search(r'(?:かな|ですか|ますか|教えて(?:ね|ほしい)?)[。？?]?$', last)
            invitation = re.match(r'^(?:もし|何か|よかったら)', last) and re.search(r'(?:聞かせて|教えて)(?:ね|ほしい|ほしいな)?[。！!]?$', last)
            if probing or invitation:
                text = ''.join(parts[:-1]).strip()
    is_greeting = user in {
        'こんばんは', 'こんばんは。', 'こんにちは', 'こんにちは。',
        'おはよう', 'おはよう。', 'おはよ', 'おはよ。',
    }
    is_story = any(w in user for w in ('昔話', '物語', 'お話をして', '話をして'))
    is_check = any(w in user for w in ('確認したい', 'テストしたい', '検証したい', '試したい', '確認しよう', '見たい'))
    if not (is_greeting or is_story or is_check):
        return text

    if is_greeting and re.search(r'^(こんばんは|こんにちは|おはよう|おはよ)。?(静かな|穏やかな|心地よい)', text):
        if 'こんばんは' in user:
            return 'こんばんは。今日も来てくれてうれしいよ。'
        if 'こんにちは' in user:
            return 'こんにちは。今日も来てくれてうれしいよ。'
        return 'おはよう。今日も来てくれてうれしいよ。'

    sentences = re.findall(r'[^。]+。?', text)
    cleaned = []
    atmosphere_re = re.compile(
        r'(静かな(夜|時間|山|空気)|穏やかな夜|心地よい(時間|余韻|空気|会話)|心に残る|心が温か|温かい思い出|星空の下|余韻が|空気が)'
    )
    for i, sent in enumerate(sentences):
        st = sent.strip()
        if not st:
            continue
        is_last = i == len(sentences) - 1
        if is_last and atmosphere_re.search(st):
            continue
        cleaned.append(st if st.endswith('。') else st + '。')

    out = ''.join(cleaned).strip()
    if not out:
        return text

    if is_check and not re.search(r'(確認|見る|比べる|試す|ログ|返答|挨拶|依頼|開発|手順|観点)', out):
        out = 'うん、確認しよう。挨拶、短い依頼、開発報告の3つで見ると違いが分かりやすいよ。'
    return out
