# src/boundary.py
from __future__ import annotations

import re
from typing import Optional


# 「境界線」要求（話題を止める/避ける）
_BOUNDARY_PAT = re.compile(
    r"(もういい|やめて|やめよう|やめよ|その話(は)?やめ|この話(は)?やめ|これ以上(は)?やめ|"
    r"中断(です|する|しよう|したい)?|いったん中断|"
    r"今それは無理|触れないで|別の話にして|別の話(が)?いい|ストップ|stop|please stop|no more)",
    re.IGNORECASE,
)


# 「止める」ではなく「軽い話に切り替える」要求
_SWITCH_PAT = re.compile(
    r"(軽い話にして|軽い話がいい|優しい空気(に)?(したい|切り替えたい)|空気(を)?切り替えたい|"
    r"話題(を)?変え(て|たい)|別の話(にして)?|軽くして)",
    re.IGNORECASE,
)


def is_boundary_request(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return False
    return _BOUNDARY_PAT.search(t) is not None


def boundary_response() -> str:
    # 境界の承認（1文）→切替の2択（軽く）→新話題へ（1文）
    return (
        "わかった、ここで止めるね。"
        "今は『静かにそばにいる』のと『軽い別の話に逃げる』なら、どっちが楽？"
        "じゃあ一旦、今日いちばんマシだった瞬間だけ拾っておく。"
    )


def is_switch_request(user_text: str) -> bool:
    """Detect a positive topic switch request (not a hard boundary)."""
    t = (user_text or "").strip()
    if not t:
        return False
    # 「やめて」等の強い境界線は boundary に任せる
    if is_boundary_request(t):
        return False
    return _SWITCH_PAT.search(t) is not None


def switch_response() -> str:
    # 承認→軽い2択→新話題（質問はここだけ）
    return (
        "うん、切り替えよう。"
        "『ふわっと雑談』と『一言だけの癒し』なら、どっちが楽？"
        "じゃあ、今日いちばんマシだった瞬間を小さく一個だけ置いておくね。"
    )


def choose_safe_topic_fallback() -> str:
    # topic_avoid で候補が死んだ時の安全雑談
    return "今は深い話じゃなくていいよ。水を一口だけでも入れておく。"
