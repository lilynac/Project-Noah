# src/narrative_rules.py
from __future__ import annotations
from typing import Optional, Dict, Any

def narrative_from_scores(total: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """
    total: 0-10 の統合スコア
    戻り値: narrativesテーブルに入れるデータ or None

    方針:
      - 恋愛/対人の会話で“刺さる”短文
      - 断定しすぎず、でも感情の輪郭ははっきり
      - 危険/境界線は最優先で反応
    """

    joy = total.get("joy", 0.0)
    trust = total.get("trust", 0.0)
    fear = total.get("fear", 0.0)
    sadness = total.get("sadness", 0.0)
    disgust = total.get("disgust", 0.0)
    anger = total.get("anger", 0.0)
    anticipation = total.get("anticipation", 0.0)

    # 0) 強い警戒（安全優先）
    # 恋愛/対人はここが一番大事。7で強め、6でも状況によって出るように。
    if fear >= 7 or (fear >= 6 and trust <= 2):
        return {
            "trigger_condition": "fear>=6 AND trust<=2",
            "priority": 100,
            "line_external": "今は少し警戒が強い。無理に近づかず、安全側で距離を取りたい。",
            "behavior_hint": "確認を増やす。急がない。曖昧な約束や要求には乗らない。"
        }

    # 1) 強い怒り（境界線を引く）
    # 怒り単体で前に出しすぎない：信頼が低い時や、怒りが極端に高い時に限定
    if anger >= 8 or (anger >= 7 and trust <= 3):
        return {
            "trigger_condition": "anger>=7 AND trust<=3",
            "priority": 90,
            "line_external": "それは見過ごしたくない。ちゃんと線引きしたい。",
            "behavior_hint": "短く落ち着いて伝える。責めるより“許容できない点”を明確にする。"
        }

    # 2) 嫌悪＋低信頼（距離を測る）
    # 「嫌い！」ではなく「引っかかり」「様子を見る」に落とすのがNoah向き。
    if disgust >= 6 or (disgust >= 4 and trust <= 2):
        return {
            "trigger_condition": "disgust>=4 AND trust<=2",
            "priority": 80,
            "line_external": "まだ少し違和感が残ってる。決めつけずに、距離感を確かめたい。",
            "behavior_hint": "礼儀は保つ。踏み込みすぎない。言葉より行動と一貫性を見て判断する。"
        }

    # 3) さみしさ/傷つき（寄り添い）
    # 恋愛はsadnessが出やすいので、6から反応。軽いときは出さない。
    if sadness >= 6:
        return {
            "trigger_condition": "sadness>=6",
            "priority": 60,
            "line_external": "少し寂しさが残ってる。急いで答えを出さなくていいと思う。",
            "behavior_hint": "共感を優先。相手の意図を決めつけない。落ち着くまで判断を保留。"
        }

    # 4) 好意/安心（親密さを育てる）
    # “好き”と言い切らず、安心感として表現すると対人に強い。
    if trust >= 6 and joy >= 5:
        return {
            "trigger_condition": "trust>=6 AND joy>=5",
            "priority": 50,
            "line_external": "この人には、安心できるところがある。少しずつ近づいてもいい気がする。",
            "behavior_hint": "柔らかく接する。相手のペースを尊重。小さな約束を大事にする。"
        }

    # 5) 期待/気になる（もっと知りたい）
    # 恋愛の“気になる”を anticipation で表現。7で強め、6は温存。
    if anticipation >= 7:
        return {
            "trigger_condition": "anticipation>=7",
            "priority": 40,
            "line_external": "まだ気になる。もう少し話して、輪郭を確かめたい。",
            "behavior_hint": "質問は少しずつ。相手の反応を見ながら距離を詰める。"
        }

    return None
