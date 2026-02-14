# src/memory/store.py
import json
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from src.db import connect


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class ImportanceResult:
    importance: float
    reasons: List[str]
    tags: List[str]
    strength: float


# まずは「軽いルール」で十分。後でLLM判定に差し替えやすいように reasons を残す。
_PREF_PAT = re.compile(r"(好き|苦手|嫌い|ハマって|推し|趣味|習慣|いつも|毎朝|毎日|だいたい)")
_EMO_PAT = re.compile(r"(嬉しい|つらい|辛い|怖い|不安|最悪|やった|達成|しんどい|泣|ムカつく)")
_PLAN_PAT = re.compile(r"(明日|明後日|来週|今週|締切|期限|予定|会議|打合せ|プロジェクト|タスク|進捗)")

_TAG_RULES = [
    ("work", re.compile(r"(仕事|職場|上司|同僚|クライアント|案件|会議|打合せ|進捗|残業)")),
    ("study", re.compile(r"(勉強|学習|資格|試験|課題|宿題|練習|復習)")),
    ("health", re.compile(r"(体調|熱|痛|頭痛|腹痛|眠|睡眠|食事|運動|筋トレ|病院|薬|メンタル)")),
    ("mood", re.compile(r"(不安|ストレス|緊張|落ち込|イライラ|焦り|しんどい|つらい|辛い)")),
    ("relationship", re.compile(r"(友達|友人|家族|母|父|兄|姉|弟|妹|恋人|彼氏|彼女|同僚|人間関係)")),
    ("media", re.compile(r"(映画|ドラマ|アニメ|漫画|マンガ|小説|本|読書|ゲーム|音楽|ライブ)")),
    ("schedule", re.compile(r"(予定|旅行|外出|予約|締切|期限|来週|今週|明日|明後日)")),
    ("noah_project", re.compile(r"(Noah|ノア|プロジェクト|実装|設計|コード|DB|スキーマ)")),
    ("memory_system", re.compile(r"(記憶|忘却|コンソリデーション|strength|importance|エピソード|要約|自己物語)")),
    ("initiative", re.compile(r"(initiative|自発|話しかけ|Opportunity|Value|Suppression)")),
    ("outing", re.compile(r"(公園|海|山|温泉|カフェ|散歩|旅行|外出|観光|美術館|映画館|レストラン)")),
    ("date_time", re.compile(r"(今日|きょう|何月|何日|曜日|何曜日|日付|何の日|記念日|誕生日)")),
    ("food", re.compile(r"(ごはん|食事|お菓子|スイーツ|甘い|チョコ|ケーキ|アイス|パン|ラーメン|カフェ)")),
    ("chat", re.compile(r"(こんにちは|こんばんは|おはよう|やあ|元気|調子どう)")),
    ("question", re.compile(r"(どう思う|教えて|わかる|知ってる|おすすめ|何がいい)")),
    ("location", re.compile(r"(どこ|公園|海|山|駅|カフェ|店|場所|近く)")),
]



def estimate_importance_and_tags(text: str, source: str) -> ImportanceResult:
    t = (text or "").strip()
    reasons: List[str] = []
    tags: List[str] = []

    # base importance
    imp = 0.25

    if _PREF_PAT.search(t):
        imp += 0.35
        reasons.append("preference/habit")
        tags.append("preference")

    if _EMO_PAT.search(t):
        imp += 0.25
        reasons.append("emotion")
        tags.append("emotion")

    if _PLAN_PAT.search(t):
        imp += 0.30
        reasons.append("plan/deadline/project")
        tags.append("plan")

    for tag, pat in _TAG_RULES:
        if pat.search(t):
            tags.append(tag)

    # 雑談/短文は薄め
    if len(t) <= 12 and not reasons:
        imp -= 0.15
        reasons.append("smalltalk/short")

    # Noah発話は「ユーザー情報の記憶」としては弱め（保存するが控えめ）
    if source == "noah":
        imp *= 0.70
        reasons.append("source:noah_discount")

    imp = _clamp01(imp)

    # 初期strength：importanceに連動（後でdecay/rehearsalで動かす）
    # 0.45〜0.95くらいに収まる感じ
    strength = _clamp01(0.45 + 0.50 * imp)

    # tagsは重複削除
    tags = sorted(set(tags))
    tags = tags[:4]
    return ImportanceResult(importance=imp, reasons=reasons, tags=tags, strength=strength)

def store_episode(text: str, source: str = "user") -> Optional[int]:
    t = (text or "").strip()
    if not t:
        return None

    est = estimate_importance_and_tags(t, source=source)

    con = connect()
    try:
        cur = con.execute(
            """
            INSERT INTO episode_memories
              (text, tags_json, importance, strength, source, importance_reasons_json)
            VALUES
              (?, ?, ?, ?, ?, ?)
            """,
            (
                t,
                json.dumps(est.tags, ensure_ascii=False),
                float(est.importance),
                float(est.strength),
                source,
                json.dumps(est.reasons, ensure_ascii=False),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()

