# src/initiative/decision.py
from __future__ import annotations

import random
import re
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
    threshold_normal: float = 0.16
    threshold_work: float = 0.60

    # cooldown（最短）
    cooldown_dont_speak_sec: int = 4 * 60        # 4分（再評価はする）
    cooldown_speak_normal_sec: int = 12 * 60
    cooldown_speak_work_sec: int = 45 * 60       # 45分（workは長め）

    # 抑制が強いほど待ちを伸ばす係数
    suppression_cooldown_boost_max: int = 6 * 60  # 最大+6分

    # 最近拒否があるときの追加待ち（強いペナルティ）
    rejected_recent_window_sec: int = 30 * 60
    rejected_extra_cooldown_sec: int = 6 * 60     # +6分

    # affection impulse: 閾値未満でも、関係性と沈黙が揃った時だけ低確率で声をかける
    affection_impulse_enabled: bool = True
    affection_impulse_base: float = 0.05
    affection_bonus_threshold: float = 0.45
    affection_bonus: float = 0.06
    trust_bonus_threshold: float = 0.40
    trust_bonus: float = 0.03
    loneliness_bonus_threshold: float = 0.30
    loneliness_bonus: float = 0.04
    long_silence_bonus_sec: int = 20 * 60
    long_silence_bonus: float = 0.06
    very_long_silence_bonus_sec: int = 3 * 60 * 60
    very_long_silence_bonus: float = 0.04
    max_affection_impulse: float = 0.18


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
        memory_ctx=None,
        affective_state: Optional[str] = None,
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
        val_res = self.val.evaluate(signals, recent_turns=recent_turns, now_ts=now, memory_ctx=memory_ctx )
        v = _clamp01(val_res.score)

        # mode別 threshold
        thr = self.cfg.threshold_work if signals.mode == "work" else self.cfg.threshold_normal

        reasons: list[str] = []

        # ★ suppressでも必ず見えるように先に計算
        final_score = opp_res.score * v

        impulse_p = self._affection_impulse_probability(
            signals,
            now=now,
            affective_state=affective_state,
            opportunity_reasons=opp_res.reasons,
        )

        debug: Dict[str, Any] = {
            "mode": signals.mode,
            "threshold": thr,
            "opportunity": {"score": opp_res.score, "reasons": opp_res.reasons},
            "value": {"score": v, "reasons": val_res.reasons, "style": val_res.style},
            "suppression": {"suppress": sup_res.suppress, "strength": sup_res.strength, "reasons": sup_res.reasons},
            "affection_impulse": {"p": impulse_p, "enabled": self.cfg.affection_impulse_enabled},
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

        # 閾値未満でも、関係性の蓄積 + 長めの沈黙があるときだけ、低確率で desire として声をかける。
        # suppression はすでに上で最優先処理済みなので、ここでは「邪魔しない範囲の小さな気まぐれ」に限定する。
        if impulse_p > 0 and random.random() < impulse_p:
            reasons.append("below_threshold")
            reasons.append(f"affection_impulse:{impulse_p:.3f}")
            try:
                debug["value"]["style"] = "desire"
                debug["affection_impulse"]["fired"] = True
            except Exception:
                pass
            cooldown = self._cooldown_for_speak(signals, sup_strength=sup_res.strength, now=now)
            return Decision(
                speak=True,
                cooldown_sec=cooldown,
                reasons=reasons,
                debug=debug,
            )

        reasons.append("below_threshold")
        try:
            debug["affection_impulse"]["fired"] = False
        except Exception:
            pass
        cooldown = self._cooldown_for_dont_speak(signals, sup_strength=sup_res.strength, now=now)
        return Decision(
            speak=False,
            cooldown_sec=cooldown,
            reasons=reasons,
            debug=debug,
        )

    def _recent_rejection_active(self, signals: InitiativeSignals, *, now: float) -> bool:
        """直近拒否が、直近のengagedで上書きされていない場合だけ有効にする。"""
        if not signals.last_rejected_at:
            return False
        if signals.last_engaged_at and signals.last_engaged_at >= signals.last_rejected_at:
            return False
        return (now - signals.last_rejected_at) <= self.cfg.rejected_recent_window_sec

    def _cooldown_for_speak(self, signals: InitiativeSignals, *, sup_strength: float, now: float) -> int:
        base = self.cfg.cooldown_speak_work_sec if signals.mode == "work" else self.cfg.cooldown_speak_normal_sec

        # suppression strength に応じて少し長くする（邪魔回避寄り）
        boost = int(self.cfg.suppression_cooldown_boost_max * _clamp01(sup_strength))
        cd = base + boost

        # 直近拒否があるならさらに長く（ただし speak 後の話なので軽めに効かせたいなら後で調整）
        if self._recent_rejection_active(signals, now=now):
            cd += int(self.cfg.rejected_extra_cooldown_sec * 0.5)

        return max(60, cd)

    def _cooldown_for_dont_speak(self, signals: InitiativeSignals, *, sup_strength: float, now: float) -> int:
        cd = self.cfg.cooldown_dont_speak_sec

        # suppression strength が高いほど待ちを伸ばす
        cd += int(self.cfg.suppression_cooldown_boost_max * _clamp01(sup_strength))

        # 最近拒否があるなら強めに伸ばす（安全側）
        if self._recent_rejection_active(signals, now=now):
            cd += self.cfg.rejected_extra_cooldown_sec

        return max(60, cd)


    def _affection_impulse_probability(
        self,
        signals: InitiativeSignals,
        *,
        now: float,
        affective_state: Optional[str] = None,
        opportunity_reasons: Optional[list[str]] = None,
    ) -> float:
        """
        関係性が育っている時だけ、小さく自発発話へ傾ける確率。
        これは通常の score を置き換えない。suppression 後・threshold 未満の補助判定としてだけ使う。
        """
        if not self.cfg.affection_impulse_enabled:
            return 0.0

        # quota 超過、連投直後、会話中、強い拒否直後は絶対に出さない。
        try:
            if signals.daily_count >= signals.daily_quota:
                return 0.0
        except Exception:
            pass

        if signals.last_noah_message_at and now - signals.last_noah_message_at < 8 * 60:
            return 0.0

        if signals.last_user_message_at and now - signals.last_user_message_at < 90:
            return 0.0

        if self._recent_rejection_active(signals, now=now):
            return 0.0

        c = int(getattr(signals, "consecutive_initiatives", 0) or 0)
        if c >= 2:
            return 0.0

        aff = self._state_float(affective_state, "affection", 0.25)
        trust = self._state_float(affective_state, "trust", 0.30)
        loneliness = self._state_float(affective_state, "loneliness", 0.15)

        p = float(self.cfg.affection_impulse_base)

        if aff >= self.cfg.affection_bonus_threshold:
            p += self.cfg.affection_bonus
        if trust >= self.cfg.trust_bonus_threshold:
            p += self.cfg.trust_bonus
        if loneliness >= self.cfg.loneliness_bonus_threshold:
            p += self.cfg.loneliness_bonus

        if signals.last_user_message_at:
            silence = max(0.0, now - signals.last_user_message_at)
            if silence >= self.cfg.long_silence_bonus_sec:
                p += self.cfg.long_silence_bonus
            if silence >= self.cfg.very_long_silence_bonus_sec:
                p += self.cfg.very_long_silence_bonus
        else:
            p *= 0.5

        if signals.mode == "work":
            p *= 0.35

        # Opportunity が「Noah直後」「quota」などを示している場合はさらに安全側。
        reasons = opportunity_reasons or []
        if any(str(r).startswith("too_soon_after_noah") for r in reasons):
            p *= 0.25
        if any(str(r).startswith("quota_exceeded") for r in reasons):
            p = 0.0

        return _clamp01(min(p, self.cfg.max_affection_impulse))

    def _state_float(self, text: Optional[str], key: str, default: float) -> float:
        if not text:
            return default
        try:
            m = re.search(rf"^\s*{re.escape(key)}\s*[:=]\s*([0-9.]+)", text, flags=re.M)
            if not m:
                return default
            return _clamp01(float(m.group(1)))
        except Exception:
            return default
