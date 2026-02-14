# src/initiative/layers.py
from __future__ import annotations

import time
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.initiative.signals import InitiativeSignals


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _exp_decay(seconds: float, half_life_sec: float) -> float:
    """
    1.0 -> 0.5 (half-life) -> 0.25 ...
    half_life_sec が小さいほど早く薄れる
    """
    if half_life_sec <= 0:
        return 0.0
    if seconds <= 0:
        return 1.0
    return 0.5 ** (seconds / float(half_life_sec))


@dataclass
class OpportunityResult:
    score: float
    reasons: List[str]


@dataclass
class OpportunityConfig:
    # 連投防止：Noah側の直近発話からの最短間隔
    min_gap_after_noah_sec: int = 8 * 60  # 8分

    # 会話が動いてる間は割り込まない：ユーザー発話直後のブロック
    conversation_block_sec: int = 90  # 90秒

    # 「間が空いた」加点の閾値（段階）
    silence_tier1_sec: int = 20 * 60   # 20分
    silence_tier2_sec: int = 60 * 60   # 60分

    # workモードの上限キャップ
    work_score_cap: float = 0.50


class OpportunityLayer:
    """
    Opportunity: 話しかけるチャンスがあるか（状況）
    - 純ルール、pureに近い（signals以外の副作用なし）
    """

    def __init__(self, cfg: Optional[OpportunityConfig] = None):
        self.cfg = cfg or OpportunityConfig()

    def evaluate(self, signals: InitiativeSignals, now_ts: Optional[float] = None) -> OpportunityResult:
        now = time.time() if now_ts is None else now_ts
        reasons: List[str] = []

        # 日跨ぎ整形（daily_countのリセットなど）
        try:
            signals.normalize(now_ts=now)
        except Exception:
            # ここで落とさない（安全側）
            pass

        # 1) quota 超えたら即0
        if signals.daily_count >= signals.daily_quota:
            return OpportunityResult(score=0.0, reasons=["quota_exceeded"])

        score = 0.2  # ベース（最短版）

        # 2) Noahの直近発話が近すぎる（連投防止）
        if signals.last_noah_message_at > 0:
            dt_noah = now - signals.last_noah_message_at
            if dt_noah < self.cfg.min_gap_after_noah_sec:
                # 近いほど強く減点（安全側）
                score *= max(0.0, dt_noah / float(self.cfg.min_gap_after_noah_sec))
                reasons.append(f"too_soon_after_noah:{int(dt_noah)}s")

        # 3) ユーザー発話直後は会話中扱い（割り込み防止）
        if signals.last_user_message_at > 0:
            dt_user = now - signals.last_user_message_at
            if dt_user < self.cfg.conversation_block_sec:
                # ほぼ話しかけない
                score *= 0.05
                reasons.append(f"conversation_active:{int(dt_user)}s")
            else:
                # 4) 間が空いたら加点（段階的）
                if dt_user >= self.cfg.silence_tier2_sec:
                    score += 0.55
                    reasons.append(f"silence_gap_t2:{int(dt_user)}s")
                elif dt_user >= self.cfg.silence_tier1_sec:
                    score += 0.35
                    reasons.append(f"silence_gap_t1:{int(dt_user)}s")
                else:
                    reasons.append(f"silence_gap_small:{int(dt_user)}s")
        else:
            # user message が未記録なら慎重（安全側で低め）
            score *= 0.5
            reasons.append("no_last_user_message")

        # 5) mode=work は上限キャップ
        if signals.mode == "work":
            if score > self.cfg.work_score_cap:
                reasons.append(f"work_cap:{self.cfg.work_score_cap}")
            score = min(score, self.cfg.work_score_cap)
        elif signals.mode != "normal":
            # 想定外modeは安全側
            score *= 0.5
            reasons.append(f"unknown_mode:{signals.mode}")

        score = _clamp01(score)

        if not reasons:
            reasons.append("default")

        return OpportunityResult(score=score, reasons=reasons)


# ---- Suppression ----

@dataclass
class SuppressionResult:
    suppress: bool
    strength: float
    reasons: List[str]


@dataclass
class SuppressionConfig:
    # rejected 直後の抑制（強）
    reject_strong_window_sec: int = 10 * 60   # 10分
    reject_weak_window_sec: int = 2 * 60 * 60 # 2時間

    # workモードの抑制ベース
    work_base_strength: float = 0.65

    # 連続自発の指数強化
    consecutive_base: float = 0.35  # 1回目以降のベース加点
    consecutive_growth: float = 1.6 # 指数係数（>1で増える）

    # weak reject の半減期
    reject_weak_half_life_sec: int = 12 * 60

    # strong reject の半減期
    reject_strong_half_life_sec: int = 120 * 60


class SuppressionLayer:
    """
    Suppression: 今は話しかけない方が良いか（邪魔回避・最優先）
    - persistent_suppressed が True なら問答無用で suppress
    - 迷いは抑制側に倒す（安全側）
    """

    def __init__(self, cfg: Optional[SuppressionConfig] = None):
        self.cfg = cfg or SuppressionConfig()

    def evaluate(
        self,
        signals: InitiativeSignals,
        now_ts: Optional[float] = None,
        *,
        persistent_suppressed: bool = False,
    ) -> SuppressionResult:
        now = time.time() if now_ts is None else now_ts
        reasons: List[str] = []

        try:
            signals.normalize(now_ts=now)
        except Exception:
            pass

        # 0) 既存 suppression（永続）が抑制中なら最優先で止める
        if persistent_suppressed:
            return SuppressionResult(
                suppress=True,
                strength=1.0,
                reasons=["persistent_suppressed"],
            )

        strength = 0.0

        # 1) workモードは強めに抑制（邪魔回避）
        if signals.mode == "work":
            strength = max(strength, self.cfg.work_base_strength)
            reasons.append(f"mode_work:{self.cfg.work_base_strength}")

        # 2) 直近で拒否/無視っぽい反応があったら強く抑制
        if signals.last_rejected_at and signals.last_rejected_at > 0:
            dt = now - signals.last_rejected_at
            if dt < 0:
                dt = 0
            if dt <= self.cfg.reject_strong_window_sec:
                # 強い抑制
                strength = max(strength, 0.95)
                reasons.append(f"recent_reject_strong:{int(dt)}s")
            elif dt <= self.cfg.reject_weak_window_sec:
                # 弱い抑制（指数減衰で自然に薄れる）
                # dt=0 のとき 0.85、時間で半減していく（12分で半分が目安）
                weak = _exp_decay(dt, self.cfg.reject_weak_half_life_sec)
                decay = 0.85 * weak
                strength = max(strength, _clamp01(decay))
                reasons.append(f"recent_reject_weak:{int(dt)}s")

        # 3) 連続自発が続くほど指数的に抑制
        c = max(0, int(getattr(signals, "consecutive_initiatives", 0) or 0))
        if c >= 2:
            # 2回目以降で強めに効かせる
            # ex: c=2 -> ~0.56, c=3 -> ~0.72, c=4 -> ~0.87
            boost = self.cfg.consecutive_base * (self.cfg.consecutive_growth ** (c - 2))
            strength = max(strength, _clamp01(boost))
            reasons.append(f"consecutive:{c}")

        strength = _clamp01(strength)

        # suppress 判定（最短：strengthが0.75以上なら止める）
        suppress = strength >= 0.75
        if suppress:
            reasons.append("suppress:true")
        else:
            reasons.append("suppress:false")

        return SuppressionResult(
            suppress=suppress,
            strength=strength,
            reasons=reasons,
        )


# ---- Value ----

@dataclass
class ValueResult:
    score: float
    reasons: List[str]
    style: str  # "micro" | "care" | "followup"


@dataclass
class ValueConfig:
    # 最近engagedの加点（この秒数以内なら少し上げる）
    engaged_window_sec: int = 30 * 60

    # 最近rejectedの減点（この秒数以内なら強めに下げる）
    rejected_window_sec: int = 30 * 60

    # topic tags がある時の継続性加点
    topic_bonus: float = 0.15

    # 困り/疲れ系の加点
    care_bonus: float = 0.35

    # 迷ったら低め（安全側）
    base_score: float = 0.20

    # 最大
    max_score: float = 0.95


class ValueLayer:
    """
    Value: 今話しかける価値があるか（嬉しさ/役立ち）
    - 最短はルールベース
    - 出力に style を含めて generation（テンプレ）へ渡す
    """

    def __init__(self, cfg: Optional[ValueConfig] = None):
        self.cfg = cfg or ValueConfig()

    def evaluate(
        self,
        signals: InitiativeSignals,
        recent_turns: Optional[List[str]] = None,
        now_ts: Optional[float] = None,
        memory_ctx=None,
    ) -> ValueResult:
        now = time.time() if now_ts is None else now_ts
        reasons: List[str] = []

        try:
            signals.normalize(now_ts=now)
        except Exception:
            pass

        text = " ".join([t for t in (recent_turns or []) if t])[:2000]
        score = float(self.cfg.base_score)
        style = "micro"

        # 1) 継続話題（topic tags）
        if signals.recent_topic_tags:
            score += self.cfg.topic_bonus
            reasons.append(f"topic_continuity:+{self.cfg.topic_bonus}")
            style = "followup"

        # 2) 困り/疲れ/詰まりの簡易検知（最近の発話から）
        if self._looks_like_need_help(text):
            score += self.cfg.care_bonus
            reasons.append(f"care_signal:+{self.cfg.care_bonus}")
            style = "care"

        # 3) engaged が最近なら少し加点
        if signals.last_engaged_at and signals.last_engaged_at > 0:
            dt = now - signals.last_engaged_at
            if dt < 0:
                dt = 0
            if dt <= self.cfg.engaged_window_sec:
                score += 0.10
                reasons.append(f"recent_engaged:{int(dt)}s:+0.10")

        # 4) rejected が最近なら価値を下げる（歓迎されない可能性）
        if signals.last_rejected_at and signals.last_rejected_at > 0:
            dt = now - signals.last_rejected_at
            if dt < 0:
                dt = 0
            if dt <= self.cfg.rejected_window_sec:
                score *= 0.35
                reasons.append(f"recent_rejected:{int(dt)}s:*0.35")
                style = "micro"

        # 5) Task3: memory があるなら「話しかける価値」を少し加点
        # narrative/summary があれば、フォローアップが作りやすい
        if memory_ctx:
            ns = memory_ctx.get("narrative") or []
            ss = memory_ctx.get("summary") or []
            if ns or ss:
                score += 0.08
                reasons.append("memory_ctx:+0.08")
                if style == "micro":
                    style = "followup"

        score = _clamp01(score)
        score = min(score, self.cfg.max_score)

        if not reasons:
            reasons.append("default_low_value")

        return ValueResult(score=score, reasons=reasons, style=style)

    def _looks_like_need_help(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()

        keys = [
            "しんど", "つら", "疲", "ねむ", "眠",
            "不安", "心配", "こわ", "怖",
            "進ま", "詰", "わから", "むず", "難",
            "困", "助け", "どうしよ", "やば",
            "stuck", "tired", "anx", "help", "overwhelm",
        ]
        return any(k in t for k in keys)
