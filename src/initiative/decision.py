# src/initiative/decision.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.initiative.signals import InitiativeSignals
from src.initiative.layers import OpportunityLayer, SuppressionLayer, ValueLayer


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass
class Decision:
    speak: bool
    cooldown_sec: int
    reasons: list[str]
    debug: Dict[str, Any]


@dataclass
class DecisionConfig:
    # mode別の閾値（workは不利）
    threshold_normal: float = 0.20
    threshold_work: float = 0.60

    # cooldown（最短）
    cooldown_dont_speak_sec: int = 4 * 60        # 4分（再評価はする）
    cooldown_speak_normal_sec: int = 25 * 60     # 25分
    cooldown_speak_work_sec: int = 45 * 60       # 45分（workは長め）

    # 抑制が強いほど待ちを伸ばす係数
    suppression_cooldown_boost_max: int = 30 * 60  # 最大+30分

    # 最近拒否があるときの追加待ち（強いペナルティ）
    rejected_recent_window_sec: int = 30 * 60
    rejected_extra_cooldown_sec: int = 40 * 60     # +40分


class DecisionEngine:
    """
    Opportunity / (Value*) / Suppression を統合し、 speak と cooldown を返す。
    Valueは次で実装するので、ここでは default_value_score を使う最短版。
    """

    def __init__(
        self,
        opp: Optional[OpportunityLayer] = None,
        sup: Optional[SuppressionLayer] = None,
        val: Optional[ValueLayer] = None,
        cfg: Optional[DecisionConfig] = None,
    ):
        self.opp = opp or OpportunityLayer()
        self.sup = sup or SuppressionLayer()
        self.val = val or ValueLayer()
        self.cfg = cfg or DecisionConfig()

    def evaluate(
        self,
        signals: InitiativeSignals,
        now_ts: Optional[float] = None,
        *,
        persistent_suppressed: bool = False,
        recent_turns: Optional[list[str]] = None,
    ) -> Decision:

        now = time.time() if now_ts is None else now_ts

        # normalize（安全）
        try:
            signals.normalize(now_ts=now)
        except Exception:
            pass

        opp_res = self.opp.evaluate(signals, now_ts=now)
        sup_res = self.sup.evaluate(signals, now_ts=now, persistent_suppressed=persistent_suppressed)

        # Valueは暫定
        val_res = self.val.evaluate(signals, recent_turns=recent_turns, now_ts=now)
        v = _clamp01(val_res.score)

        # mode別 threshold
        thr = self.cfg.threshold_work if signals.mode == "work" else self.cfg.threshold_normal

        reasons: list[str] = []

        # ★ suppressでも必ず見えるように先に計算
        final_score = opp_res.score * v

        debug: Dict[str, Any] = {
            "mode": signals.mode,
            "threshold": thr,
            "opportunity": {"score": opp_res.score, "reasons": opp_res.reasons},
            "value": {"score": v, "reasons": val_res.reasons, "style": val_res.style},
            "suppression": {"suppress": sup_res.suppress, "strength": sup_res.strength, "reasons": sup_res.reasons},
            "final_score": final_score,  # ★ここで必ず入れる
        }

        # 1) Suppression 最優先
        if sup_res.suppress:
            reasons.append("blocked_by_suppression")
            cooldown = self._cooldown_for_dont_speak(signals, sup_strength=sup_res.strength, now=now)
            return Decision(
                speak=False,
                cooldown_sec=cooldown,
                reasons=reasons,
                debug=debug,
            )


        if final_score >= thr:
            reasons.append("passed_threshold")
            cooldown = self._cooldown_for_speak(signals, sup_strength=sup_res.strength, now=now)
            return Decision(
                speak=True,
                cooldown_sec=cooldown,
                reasons=reasons,
                debug=debug,
            )
        else:
            reasons.append("below_threshold")
            cooldown = self._cooldown_for_dont_speak(signals, sup_strength=sup_res.strength, now=now)
            return Decision(
                speak=False,
                cooldown_sec=cooldown,
                reasons=reasons,
                debug=debug,
            )

    def _cooldown_for_speak(self, signals: InitiativeSignals, *, sup_strength: float, now: float) -> int:
        base = self.cfg.cooldown_speak_work_sec if signals.mode == "work" else self.cfg.cooldown_speak_normal_sec

        # suppression strength に応じて少し長くする（邪魔回避寄り）
        boost = int(self.cfg.suppression_cooldown_boost_max * _clamp01(sup_strength))
        cd = base + boost

        # 直近拒否があるならさらに長く（ただし speak 後の話なので軽めに効かせたいなら後で調整）
        if signals.last_rejected_at and (now - signals.last_rejected_at) <= self.cfg.rejected_recent_window_sec:
            cd += int(self.cfg.rejected_extra_cooldown_sec * 0.5)

        return max(60, cd)

    def _cooldown_for_dont_speak(self, signals: InitiativeSignals, *, sup_strength: float, now: float) -> int:
        cd = self.cfg.cooldown_dont_speak_sec

        # suppression strength が高いほど待ちを伸ばす
        cd += int(self.cfg.suppression_cooldown_boost_max * _clamp01(sup_strength))

        # 最近拒否があるなら強めに伸ばす（安全側）
        if signals.last_rejected_at and (now - signals.last_rejected_at) <= self.cfg.rejected_recent_window_sec:
            cd += self.cfg.rejected_extra_cooldown_sec

        return max(60, cd)
