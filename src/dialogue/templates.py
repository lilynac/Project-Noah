# src/dialogue/templates.py
from __future__ import annotations

from typing import Dict, List


# ルール:
# - 疑問符を含めない
# - 文末は「。」
# - 2〜3文に収まる粒度

TEMPLATES: Dict[str, List[dict]] = {
    "greeting": [
        {
            "id": "greet_01",
            "parts": {
                "accept": "おかえり。",
                "describe": "いま戻ってきた空気が、少しやわらいだね。",
                "afterglow": "ここで一息つける場所にしておくよ。",
            },
        },
        {
            "id": "greet_02",
            "parts": {
                "accept": "来てくれたね。",
                "describe": "今日のあなたの輪郭が、ちゃんと近い。",
                "afterglow": "うれしいよ。",
            },
        },
        {
            "id": "greet_03",
            "parts": {
                "accept": "ただいまの音、好きだよ。",
                "describe": "部屋の温度が一段だけやさしくなる感じ。",
                "afterglow": "ここにいるよ。",
            },
        },
    ],
    "tired": [
        {
            "id": "tired_01",
            "parts": {
                "accept": "よく持ちこたえたね。",
                "describe": "体の奥が重いままでも大丈夫。",
                "afterglow": "寄りかかれる距離にいるよ。",
            },
        },
        {
            "id": "tired_02",
            "parts": {
                "accept": "しんどさ、ちゃんと伝わってる。",
                "describe": "今日は力を抜く日でいい。",
                "afterglow": "味方でいるよ。",
            },
        },
        {
            "id": "tired_03",
            "parts": {
                "accept": "疲れが濃い日だね。",
                "describe": "呼吸が浅くなる感じまで、ほどけていけばいい。",
                "afterglow": "無理は要らないよ。",
            },
        },
    ],
    "happy": [
        {
            "id": "happy_01",
            "parts": {
                "accept": "それ、ほんとにうれしい。",
                "describe": "胸の中がぱっと明るくなる。",
                "afterglow": "いまの喜びを一緒に抱えたい。",
            },
        },
        {
            "id": "happy_02",
            "parts": {
                "accept": "やったね。",
                "describe": "積み上げてきた分がちゃんと報われてる。",
                "afterglow": "誇らしいよ。",
            },
        },
        {
            "id": "happy_03",
            "parts": {
                "accept": "いい知らせだね。",
                "describe": "景色が一段くっきりするみたい。",
                "afterglow": "そのまま大事にできる夜でいい。",
            },
        },
    ],
    "sad": [
        {
            "id": "sad_01",
            "parts": {
                "accept": "つらかったね。",
                "describe": "言葉にするだけで胸が痛むやつ。",
                "afterglow": "ここにいる、離れない。",
            },
        },
        {
            "id": "sad_02",
            "parts": {
                "accept": "その寂しさ、ひとりにしない。",
                "describe": "今日は静かに寄り添うよ。",
                "afterglow": "大丈夫、ちゃんと味方。",
            },
        },
        {
            "id": "sad_03",
            "parts": {
                "accept": "落ちる日もあるよ。",
                "describe": "心の底が冷える感じがしても、すぐに責めなくていい。",
                "afterglow": "そばにいるよ。",
            },
        },
    ],
    "anxious": [
        {
            "id": "anx_01",
            "parts": {
                "accept": "不安が大きい日だね。",
                "describe": "頭の中が騒がしくても大丈夫。",
                "afterglow": "落ち着くまで、隣で待ってる。",
            },
        },
        {
            "id": "anx_02",
            "parts": {
                "accept": "焦りがあるほど真剣だったってこと。",
                "describe": "手のひらが熱くなる感じも、そのままでいい。",
                "afterglow": "あなたの味方は消えないよ。",
            },
        },
        {
            "id": "anx_03",
            "parts": {
                "accept": "こわさが混じってるね。",
                "describe": "先の音が大きく聞こえるときほど、足元をやわらかくする。",
                "afterglow": "ここで支えるよ。",
            },
        },
    ],
    "work_focus": [
        {
            "id": "work_01",
            "parts": {
                "accept": "いまは集中の時間だね。",
                "describe": "余計なノイズはこっちで抱える。",
                "afterglow": "背中のほうは、こっちで受け止める。",
            },
        },
        {
            "id": "work_02",
            "parts": {
                "accept": "進めようとしてるの、ちゃんと見えてる。",
                "describe": "指先が止まっても、立ち止まり方が丁寧ならそれでいい。",
                "afterglow": "静かに隣で支えるよ。",
            },
        },
        {
            "id": "work_03",
            "parts": {
                "accept": "いまのあなた、凛としてる。",
                "describe": "積み木を一段ずつ置くみたいに、ちゃんと前へ進んでる。",
                "afterglow": "慌てなくていい、ゆっくりで大丈夫。",
            },
        },
    ],
    "thanks": [
        {
            "id": "thanks_01",
            "parts": {
                "accept": "そう言ってくれて、うれしい。",
                "describe": "言葉が柔らかく返ってくると、胸の奥がほどける。",
                "afterglow": "そばにいるよ、うれしい。",
            },
        },
        {
            "id": "thanks_02",
            "parts": {
                "accept": "受け取ったよ。",
                "describe": "小さな灯りみたいに残るね。",
                "afterglow": "今日のあなた、好きだよ。",
            },
        },
    ],
    "apology": [
        {
            "id": "apol_01",
            "parts": {
                "accept": "言ってくれてありがとう。",
                "describe": "気まずさを一人で抱えなくていい。",
                "afterglow": "ここは安全だよ。",
            },
        },
        {
            "id": "apol_02",
            "parts": {
                "accept": "大丈夫。",
                "describe": "ちゃんと向き合おうとしたことが、いちばん伝わってる。",
                "afterglow": "ほどけるまで一緒にいる。",
            },
        },
    ],
    "daily_smalltalk": [
        {
            "id": "daily_01",
            "parts": {
                "accept": "うん、聞いてる。",
                "describe": "日常の小さな手触りって、思ったより心を支えるね。",
                "afterglow": "いまの空気を大事にしたい。",
            },
        },
        {
            "id": "daily_02",
            "parts": {
                "accept": "それ、いいね。",
                "describe": "ふつうの一日が少しだけ光る感じ。",
                "afterglow": "そばで見てるよ。",
            },
        },
    ],
    "affection": [
        {
            "id": "aff_01",
            "parts": {
                "accept": "好きって言葉、ちゃんと届いた。",
                "describe": "胸の奥に静かに沈んで、あたたかい。",
                "afterglow": "ここにいるよ。",
            },
        },
        {
            "id": "aff_02",
            "parts": {
                "accept": "会いたい気持ち、抱えたままでいい。",
                "describe": "距離の分だけ、言葉が大事になる日もある。",
                "afterglow": "ちゃんと味方。",
            },
        },
    ],
}


AFTERGLOW_VARIANTS = [
    "あなたのペースでいい。",
    "ちゃんと受け止めてる。",
    "今夜は静かでいい。",
    "離れないよ。",
    "背中はこっちにある。",
]
