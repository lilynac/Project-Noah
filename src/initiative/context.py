"""
initiative context helpers

- research（余韻）注入の判定/抽出を Noah.py から切り離し、
  src/initiative 配下で完結させるためのモジュール。
"""

from __future__ import annotations


# NOTE:
# ここには「initiative演出（research注入など）」のロジックだけを置く。
# Noah.py 側にはパス解決・抽出・日次上限などのルールを戻さない。


def read_last_research_block(research_path: str) -> str:
    import os

    if not os.path.exists(research_path):
        return ""
    with open(research_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return ""
    blocks = text.split("\n\n")
    return blocks[-1]


def extract_research_phrase(block: str) -> str:
    if not block:
        return ""

    lines = block.splitlines()
    memo = next((l for l in lines if l.startswith("メモ:")), "")
    if not memo:
        return ""

    phrase = memo.replace("メモ:", "").strip()
    if len(phrase) > 40:
        phrase = phrase[:40].rstrip(" 。、") + "…"
    return phrase


def should_inject_research(
    *,
    now_date,
    initiative_count: int,
    injected_today: int,
    last_injected_date,
    is_work_mode: bool,
    daily_cap: int = 2,
    every_n: int = 5,
) -> bool:
    """
    research（余韻）を注入してよいかの判定。
    Runner（Noah.py）側の状態を引数でもらうことで、Noah.py 依存を断つ。
    """
    # 日付が変わったら、実質 0 回扱い（カウンタのリセットは Runner 側で行う）
    if last_injected_date != now_date:
        injected_today = 0

    # 1日の上限
    if injected_today >= daily_cap:
        return False

    # n回に1回だけ注入（initiative_count は "今回の発話のカウントが進んだ後" を想定）
    if every_n > 0 and (initiative_count % every_n != 0):
        return False

    # workモード中は注入しない
    if is_work_mode:
        return False

    return True


def build_research_phrase(
    *,
    research_path: str,
    now_date,
    initiative_count: int,
    injected_today: int,
    last_injected_date,
    is_work_mode: bool,
    daily_cap: int = 2,
    every_n: int = 5,
) -> str:
    """
    research注入の可否判定〜phrase抽出までをまとめて行い、
    generate_initiative_text に渡す research_phrase を返す。
    """
    ok = should_inject_research(
        now_date=now_date,
        initiative_count=initiative_count,
        injected_today=injected_today,
        last_injected_date=last_injected_date,
        is_work_mode=is_work_mode,
        daily_cap=daily_cap,
        every_n=every_n,
    )
    if not ok:
        return ""

    block = read_last_research_block(research_path)
    return extract_research_phrase(block)
