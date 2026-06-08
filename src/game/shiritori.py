from __future__ import annotations

import re
from typing import Optional, Tuple


# 超軽量のしりとり。
# - 辞書は持たず、最低限「つながる」体験を優先
# - 「ん」で終わる単語は避ける


_KATA2HIRA = str.maketrans(
    {chr(code): chr(code - 0x60) for code in range(0x30A1, 0x30F7)}
)


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = s.translate(_KATA2HIRA)
    # ひらがな・長音・小書きを残しつつ、記号や空白を落とす
    s = re.sub(r"[^ぁ-んー]", "", s)
    return s


def _last_kana(s: str) -> str:
    s = _norm(s)
    if not s:
        return ""
    # 長音はひとつ前
    if s.endswith("ー") and len(s) >= 2:
        return s[-2]
    return s[-1]


# 最小の候補辞書（頻出のかなをカバー）
_BANK = {
    "ご": ["ごりら", "ごはん", "ごま", "ごえん"],
    "ま": ["まくら", "まめ", "まつり", "まど"],
    "り": ["りんご", "りす", "りぼん", "りょうり"],
    "す": ["すいか", "すずめ", "すみれ"],
    "ん": ["りんご"],  # 使わない
    "あ": ["あめ", "あさ", "あひる"],
    "い": ["いぬ", "いす", "いちご"],
    "う": ["うさぎ", "うみ", "うた"],
    "え": ["えんぴつ", "えび", "えき"],
    "お": ["おちゃ", "おにぎり", "おと"],
    "か": ["かめ", "かさ", "かに"],
    "き": ["きつね", "きのこ", "きりん"],
    "さ": ["さくら", "さかな", "さとう"],
    "た": ["たぬき", "たまご", "たび"],
    "な": ["なす", "なみ", "なべ"],
    "は": ["はな", "はさみ", "はる"],
    "ひ": ["ひつじ", "ひこうき", "ひまわり"],
    "ふ": ["ふね", "ふくろ", "ふゆ"],
    "へ": ["へび", "へや"],
    "ほ": ["ほし", "ほたる"],
    "や": ["やま", "やさい"],
    "ゆ": ["ゆき", "ゆび"],
    "よ": ["よる", "よこ"],
    "ら": ["らいおん", "らっぱ"],
    "る": ["るすばん", "るり"],
    "れ": ["れもん", "れんげ"],
    "ろ": ["ろうそく", "ろば"],
    "わ": ["わに", "わら"],
}


def start() -> Tuple[str, str]:
    """(bot_word, last_char)"""
    w = "りんご"
    return w, _last_kana(w)


def reply(user_word: str, expected_start: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Return (bot_word_or_none, new_expected_start, error_or_none)."""
    uw = _norm(user_word)
    if not uw:
        return None, expected_start, "言葉をひとつだけ送って。"

    # つながりチェック
    if expected_start and not uw.startswith(expected_start):
        return None, expected_start, f"『{expected_start}』から始まる言葉でお願い。"

    # 「ん」で終わったら負け扱い（ただし責めない）
    if _last_kana(uw) == "ん":
        return None, expected_start, "『ん』で終わったから、ここでいったんおしまい。もう一回やるなら言って。"

    next_start = _last_kana(uw)
    cand = [c for c in _BANK.get(next_start, []) if _last_kana(c) != "ん"]
    if not cand:
        # フォールバック：次の開始文字を返すだけ
        return None, next_start, None
    bot = cand[0]
    return bot, _last_kana(bot), None
