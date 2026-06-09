# src/initiative/signals.py
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _today_key(now_ts: Optional[float] = None) -> str:
    ts = now_ts if now_ts is not None else time.time()
    # ローカル日付（Noah実行環境のタイムゾーン）でOK。後で統一したくなったら差し替え。
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _safe_str(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v)
    except Exception:
        return default


def _safe_list_str(v: Any) -> List[str]:
    if not v:
        return []
    if isinstance(v, list):
        out: List[str] = []
        for x in v:
            s = _safe_str(x, "")
            if s:
                out.append(s)
        return out
    # 変な型で入ってたら諦める
    return []


def _get_memory_dir() -> Path:
    """
    既存プロジェクトの MEMORY_DIR を尊重する。
    import が通らない場合のためにフォールバックも用意。
    """
    # パターン1: src.paths
    try:
        from src.paths import MEMORY_DIR  # type: ignore
        return Path(MEMORY_DIR)
    except Exception:
        pass

    # パターン2: paths（相対）
    try:
        from paths import MEMORY_DIR  # type: ignore
        return Path(MEMORY_DIR)
    except Exception:
        pass

    # フォールバック（最悪でも動く）
    return Path(os.getcwd()) / "data" / "memory"


DEFAULT_DAILY_QUOTA = 5
DEFAULT_TOPIC_MAX = 8


@dataclass
class InitiativeSignals:
    # required concepts
    last_user_message_at: float = 0.0
    last_noah_message_at: float = 0.0
    last_engaged_at: float = 0.0
    last_rejected_at: float = 0.0

    mode: str = "normal"  # "work" or "normal"
    recent_topic_tags: List[str] = field(default_factory=list)

    daily_quota: int = DEFAULT_DAILY_QUOTA
    daily_count: int = 0
    date_key: str = field(default_factory=_today_key)

    consecutive_initiatives: int = 0

    # tuning knobs (optional but handy)
    topic_max: int = DEFAULT_TOPIC_MAX

    def normalize(self, now_ts: Optional[float] = None) -> None:
        """
        壊れた値や古いdate_keyを整える。ロード直後に呼ぶ想定。
        """
        now_ts = time.time() if now_ts is None else now_ts
        today = _today_key(now_ts)

        # mode を矯正
        if self.mode not in ("work", "normal"):
            self.mode = "normal"

        # 日跨ぎなら daily_count リセット
        if self.date_key != today:
            self.date_key = today
            self.daily_count = 0
            self.consecutive_initiatives = 0

        # quota の下限
        if self.daily_quota <= 0:
            self.daily_quota = DEFAULT_DAILY_QUOTA

        # topic max の下限
        if self.topic_max <= 0:
            self.topic_max = DEFAULT_TOPIC_MAX

        # recent_topic_tags をリング化
        self.recent_topic_tags = self.recent_topic_tags[-self.topic_max :]

        # 時刻が未来になってたら丸める（安全側）
        for attr in ("last_user_message_at", "last_noah_message_at", "last_engaged_at", "last_rejected_at"):
            v = getattr(self, attr, 0.0)
            if v > now_ts + 5:
                setattr(self, attr, now_ts)

        if self.daily_count < 0:
            self.daily_count = 0
        if self.consecutive_initiatives < 0:
            self.consecutive_initiatives = 0

    def push_topic_tags(self, tags: List[str]) -> None:
        """
        topic tag を後ろに追加して、重複を軽く整理しつつリングにする。
        """
        if not tags:
            return
        clean = []
        for t in tags:
            t = (t or "").strip()
            if not t:
                continue
            clean.append(t)

        if not clean:
            return

        # 直近重複は落とす（完全な重複だけ）
        for t in clean:
            if self.recent_topic_tags and self.recent_topic_tags[-1] == t:
                continue
            self.recent_topic_tags.append(t)

        self.recent_topic_tags = self.recent_topic_tags[-self.topic_max :]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InitiativeSignals":
        s = cls()
        s.last_user_message_at = _safe_float(d.get("last_user_message_at"), 0.0)
        s.last_noah_message_at = _safe_float(d.get("last_noah_message_at"), 0.0)
        s.last_engaged_at = _safe_float(d.get("last_engaged_at"), 0.0)
        s.last_rejected_at = _safe_float(d.get("last_rejected_at"), 0.0)

        s.mode = _safe_str(d.get("mode"), "normal")
        s.recent_topic_tags = _safe_list_str(d.get("recent_topic_tags"))

        s.daily_quota = _safe_int(d.get("daily_quota"), DEFAULT_DAILY_QUOTA)
        s.daily_count = _safe_int(d.get("daily_count"), 0)
        s.date_key = _safe_str(d.get("date_key"), _today_key())

        s.consecutive_initiatives = _safe_int(d.get("consecutive_initiatives"), 0)

        s.topic_max = _safe_int(d.get("topic_max"), DEFAULT_TOPIC_MAX)

        s.normalize()
        return s


def default_signals() -> InitiativeSignals:
    s = InitiativeSignals()
    s.normalize()
    return s


def signals_path(filename: str = "initiative_signals.json") -> Path:
    mem = _get_memory_dir()
    return mem / filename


def load_signals(path: Optional[Path] = None) -> InitiativeSignals:
    p = path or signals_path()
    try:
        if not p.exists():
            return default_signals()

        raw = p.read_text(encoding="utf-8")
        d = json.loads(raw)
        if not isinstance(d, dict):
            return default_signals()
        return InitiativeSignals.from_dict(d)
    except Exception:
        # 壊れてても復旧（安全側）
        return default_signals()


def save_signals(signals: InitiativeSignals, path: Optional[Path] = None) -> None:
    p = path or signals_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    signals.normalize()
    tmp = p.with_suffix(p.suffix + ".tmp")

    data = signals.to_dict()
    # atomic-ish write
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


# ---- update helpers ----
def rollover_day_if_needed(signals: InitiativeSignals, now_ts: Optional[float] = None) -> None:
    """
    日跨ぎリセット（initiative_loop 側などで周期的に呼べる）
    """
    signals.normalize(now_ts=now_ts)


def set_mode(signals: InitiativeSignals, mode: str, now_ts: Optional[float] = None) -> None:
    """
    mode同期。ついでに日跨ぎも整える。
    """
    if mode in ("work", "normal"):
        signals.mode = mode
    signals.normalize(now_ts=now_ts)


def touch_user_message(
    signals: InitiativeSignals,
    user_text: str,
    now_ts: Optional[float] = None,
    *,
    engaged: Optional[bool] = None,
    rejected: Optional[bool] = None,
    topic_tags: Optional[List[str]] = None,
) -> None:
    """
    ユーザー発話が来たときに呼ぶ“固定ルール”更新。

    - last_user_message_at は必ず更新
    - engaged/rejected が判定できるなら last_engaged_at/last_rejected_at を更新
    - ユーザーが返してきた = 会話が続いた扱いなので consecutive_initiatives をリセット
    - topic_tags があればリングに追加
    """
    now_ts = time.time() if now_ts is None else now_ts
    signals.normalize(now_ts=now_ts)

    signals.last_user_message_at = now_ts
    signals.consecutive_initiatives = 0  # ユーザー反応が来たら連続自発は途切れた扱い

    # 明示フラグがあればそれを優先
    if engaged is True:
        signals.last_engaged_at = now_ts
        # ユーザーが戻ってきて普通に反応したなら、過去の「拒否っぽさ」は解消する。
        # これをしないと、挨拶や短い返事の後も initiative 側で recent_rejected が残り続ける。
        if rejected is not True and signals.last_rejected_at and signals.last_rejected_at <= now_ts:
            signals.last_rejected_at = 0.0
    if rejected is True:
        signals.last_rejected_at = now_ts

    # topic tags
    if topic_tags:
        signals.push_topic_tags(topic_tags)
    else:
        # ここは雑でOK。必要なら後で抜く/強化する
        tags = extract_topic_tags_simple(user_text)
        if tags:
            signals.push_topic_tags(tags)


def touch_noah_message(
    signals: InitiativeSignals,
    now_ts: Optional[float] = None,
    *,
    is_initiative: bool = True,
) -> None:
    """
    Noahがメッセージを出したときに呼ぶ。

    - last_noah_message_at 更新
    - 自発発話なら daily_count++, consecutive_initiatives++
    """
    now_ts = time.time() if now_ts is None else now_ts
    signals.normalize(now_ts=now_ts)

    signals.last_noah_message_at = now_ts

    if is_initiative:
        signals.daily_count += 1
        signals.consecutive_initiatives += 1


def extract_topic_tags_simple(text: str) -> List[str]:
    """
    最短のtopic tag抽出（雑でOK）。後でタスク3に合わせて強化前提。
    - まずは「短いキーワードっぽいもの」を拾う
    """
    if not text:
        return []
    t = text.strip().lower()

    # 露骨な作業/感情/健康系だけ先に拾う（例）
    seeds = {
        "疲れ": ["tired", "sleep", "眠", "つかれ", "疲"],
        "仕事": ["work", "task", "締切", "仕事", "作業", "issue", "pr"],
        "不安": ["anx", "不安", "こわ", "怖", "心配"],
        "嬉しい": ["happy", "嬉", "よかった", "最高"],
        "詰まり": ["stuck", "詰", "進ま", "わから", "むず"],
    }

    found: List[str] = []
    for tag, keys in seeds.items():
        for k in keys:
            if k in t:
                found.append(tag)
                break

    # 最大3つまで（雑談化しないため）
    return found[:3]
