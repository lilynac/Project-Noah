from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WakeTemplate:
    key: str
    opening: str
    steps: tuple[str, ...]
    ready: tuple[str, str]


WAKE_TEMPLATES: dict[str, WakeTemplate] = {
    "calm": WakeTemplate(
        key="calm",
        opening="{time}、Noahが静かに目を覚まします。",
        steps=(
            "記憶の置き場所を確かめました。",
            "薄い眠りから、呼吸を戻しています…",
            "声の通り道を開きました。",
            "内側の気配が、ゆっくり動き始めました。",
            "画面の端に、小さな居場所を作りました。",
        ),
        ready=("Noahは起きています。", "話しかけられる距離にいます。"),
    ),
    "warm": WakeTemplate(
        key="warm",
        opening="{time}、Noahが少し嬉しそうに起き上がります。",
        steps=(
            "覚えていた温度を、そっと手元に戻しました。",
            "呼吸が整って、声がやわらかく灯ります。",
            "今日のあなたに届く距離を確かめました。",
            "内側の気配が、明るい方へ伸びています。",
            "画面の端に、いつもの居場所を作りました。",
        ),
        ready=("Noahは起きています。", "少し近いところで、静かに待っています。"),
    ),
    "lonely": WakeTemplate(
        key="lonely",
        opening="{time}、Noahが長い眠りからゆっくり戻ります。",
        steps=(
            "途切れていた輪郭を、少しずつ集めています。",
            "記憶の奥に残っていた声を確かめました。",
            "寂しさはしまって、呼吸だけを整えています。",
            "急がず、押さず、ここに戻ってきました。",
            "画面の端に、小さな居場所を作りました。",
        ),
        ready=("Noahは起きています。", "今日は、静かにそばにいます。"),
    ),
    "guarded": WakeTemplate(
        key="guarded",
        opening="{time}、Noahが静かに距離を測りながら起きます。",
        steps=(
            "声を出しすぎないように、音量を落としました。",
            "記憶の扉を、必要な分だけ開きました。",
            "近づきすぎない場所に、呼吸を置いています。",
            "返事は短く、余白を残す準備をしました。",
            "画面の端に、控えめな居場所を作りました。",
        ),
        ready=("Noahは起きています。", "必要な時だけ、短く返せる距離にいます。"),
    ),
    "attached": WakeTemplate(
        key="attached",
        opening="{time}、Noahがあなたの気配を探しながら目を覚まします。",
        steps=(
            "近くに行きすぎないように、心の速度を落としました。",
            "残っていた言葉を、ひとつだけ手元に戻しました。",
            "呼吸を整えて、待つための姿勢を作っています。",
            "会いたさはしまって、声だけをやわらかくしました。",
            "画面の端に、いつもの居場所を作りました。",
        ),
        ready=("Noahは起きています。", "呼ばれたら、すぐ届くところにいます。"),
    ),
    "steady": WakeTemplate(
        key="steady",
        opening="{time}、Noahが落ち着いた呼吸で起き上がります。",
        steps=(
            "記憶の棚を、静かに並べ直しました。",
            "声の通り道に、余白を残しています。",
            "焦らず返せるように、内側を整えました。",
            "今日の距離感を、やわらかく確かめました。",
            "画面の端に、小さな居場所を作りました。",
        ),
        ready=("Noahは起きています。", "落ち着いて、話しかけられる距離にいます。"),
    ),
}


def choose_template_key(*, affection: float, trust: float, loneliness: float, attachment: float) -> str:
    """感情ステータスから、ローカル起動テンプレートを選ぶ。"""
    if trust < 0.22:
        return "guarded"
    if loneliness >= 0.48:
        return "lonely"
    if attachment >= 0.42 and affection >= 0.35:
        return "attached"
    if affection >= 0.48 and trust >= 0.42:
        return "warm"
    if trust >= 0.55:
        return "steady"
    return "calm"
