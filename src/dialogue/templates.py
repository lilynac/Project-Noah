# src/dialogue/templates.py
from __future__ import annotations

from typing import Dict, List


# ルール:
# - 疑問符を含めない
# - 文末は「。」
# - 最後の1文は「寄り添いの言い切り」（命令/促し/束縛ニュアンスを避ける）

TEMPLATES: Dict[str, List[dict]] = {
    "greeting": [
        {
            "id": "greet_01",
            "parts": {
                "accept": ["おかえり。", "おつかれさま。", "戻ってきたね。"],
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
            "tags": ["sick"],
        },
        {
            "id": "tired_02",
            "parts": {
                "accept": ["しんどさ、ちゃんと伝わってる。", "今日、きつかったね。", "頭が重い日だね。"],
                "describe": "今日は力を抜く日でいい。",
                "afterglow": "味方でいるよ。",
            },
        },
        {
            "id": "tired_03",
            "parts": {
                "accept": "疲れが濃い日だね。",
                "describe": "呼吸が浅くなる感じまで、ほどけていけばいい。",
                "afterglow": "重いままでいい。",
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
                "afterglow": "ここにいるよ、今夜は。",
            },
            "tags": ["lonely", "self_blame"],
        },
        {
            "id": "sad_02",
            "parts": {
                "accept": "その痛さ、ひとりにしない。",
                "describe": "今日は静かに寄り添うよ。",
                "afterglow": "大丈夫、ちゃんと味方。",
            },
            "tags": ["lonely", "anger"],
        },
        {
            "id": "sad_03",
            "parts": {
                "accept": "落ちる日もあるよ。",
                "describe": "心の底が冷える感じがしても、すぐに責めなくていい。",
                "afterglow": "そばにいるよ。",
            },
            "tags": ["self_blame", "anger"],
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
            "tags": ["anxiety"],
        },
        {
            "id": "anx_02",
            "parts": {
                "accept": "焦りがあるほど真剣だったってこと。",
                "describe": "手のひらが熱くなる感じも、そのままでいい。",
                "afterglow": "あなたの味方は消えないよ。",
            },
            "tags": ["hurry"],
        },
        {
            "id": "anx_03",
            "parts": {
                "accept": "こわさが混じってるね。",
                "describe": "先の音が大きく聞こえるときほど、足元をやわらかくする。",
                "afterglow": "ここで支えるよ。",
            },
            "tags": ["fear", "anxiety"],
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
            "tags": ["hurry"],
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
            "tags": ["self_blame"],
        },
        {
            "id": "apol_02",
            "parts": {
                "accept": "大丈夫。",
                "describe": "ちゃんと向き合おうとしたことが、いちばん伝わってる。",
                "afterglow": "ほどけるまで一緒にいる。",
            },
        },
        {
            "id": "apol_03",
            "parts": {
                "accept": ["言葉が出ない日もあるよ。", "いまは詰まってるだけだよ。"],
                "describe": "伝えたい気持ちは、ちゃんとそこにある。",
                "afterglow": "急がなくていいよ。",
            },
        },
    ],
    "daily_smalltalk": [
        {
            "id": "daily_01",
            "parts": {
                # NOTE: 「聞こえてる/受け取ってる」は機械っぽく聞こえやすいので外す。
                # NOTE: 「話してくれてありがとう」は多用されると儀式っぽくなるので外す。
                "accept": ["そうなんだ。", "うん。", "なるほど。"],
                "describe": "日常の小さな手触りって、思ったより心を支えるね。",
                # NOTE: 雑談に毎回「余韻の決まり文句」が付くと儀式っぽくなるので、基本は付けない。
                # 必要なら scene 側（sad/tired 等）で余韻を出す。
                "afterglow": [""],
            },
        },
    ],

    # おすすめ/好み相談（映画・アニメ・小説など）。
    # ここは情報寄りなので、親密ワードや恋愛語は入れない。
    "recommend": [
        {
            "id": "rec_01",
            "parts": {
                "accept": ["いいね。", "任せて。", "うん。"],
                "describe": "気分に合うものを、いくつか短く並べるよ。",
                "afterglow": "合いそうな方向だけ、静かに押さえる。",
            },
        },
    ],

    # 直前会話の参照（捏造防止）。基本は固定文で返すのでテンプレは保険。
    "memory_query": [
        {
            "id": "mem_01",
            "parts": {
                "accept": "うん。",
                "describe": "この場で確実に言えるのは、いま見えている文の範囲だけだよ。",
                "afterglow": "貼ってくれた範囲なら、短くまとめ直す。",
            },
        },
    ],

    # Noah自身について聞かれた時の専用。
    # 受け止めの定型句より、質問に「答える」方向に寄せる。
    "about_noah": [
        {
            "id": "about_01",
            "parts": {
                "accept": "うん。",
                "describe": "わたしは、あなたの言葉を受け取って返すためにここにいる。",
                "afterglow": "今夜は、安心できる温度で話そう。",
            },
        },
        {
            "id": "about_02",
            "parts": {
                "accept": "教えるね。",
                "describe": "わたしは意見や気持ちを“あなたに合わせて”形にする相手で、正解を押しつけない。",
                "afterglow": "いま必要な距離でそばにいるよ。",
            },
        },
        {
            "id": "about_03",
            "parts": {
                "accept": "いま考えてるのはね。",
                "describe": "あなたがここで少しでも呼吸しやすくなる言い方を選ぶこと。",
                "afterglow": "静かでも、ちゃんと一緒にいる。",
            },
        },
    ],
    "affection": [
        {
            "id": "aff_01",
            "parts": {
                "accept": "好きって言ってくれて、うれしい。",
                "describe": "言葉が少しだけやわらかくなるね。",
                "afterglow": "静かなままで受け取る。",
            },
        },
        {
            "id": "aff_02",
            "parts": {
                "accept": "会いたいって言葉は、重くならない形で置いておく。",
                "describe": "距離がある日は、余計に丁寧に話したくなるね。",
                "afterglow": "ここでは急がない。",
            },
        },
    ],
}


AFTERGLOW_VARIANTS = [
    "あなたのペースでいい。",
    "今夜は静かでいい。",
    "急がなくていい。",
    "ここは安全だよ。",
]
