"""Persistent experiences and plans for Noah's life between conversations.

No network calls or runtime file access at import time. One store is shared by
the chat, scheduler and UI; writes are atomic and API work runs outside its lock.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import math
import os
import re
import unicodedata
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4


RESEARCH_DAILY_LIMIT = 2
TALK_DAILY_LIMIT = 8
INTEREST_PILLARS = {
    "expression": "自分の表現と存在",
    "user": "あなたへの関心",
    "curiosity": "自分だけの好奇心",
}


def interest_pillar(item):
    value = item.get("pillar")
    return value if value in INTEREST_PILLARS else ("user" if item.get("origin") == "conversation" else "curiosity")


def text(value, limit=240):
    return value.strip()[:limit] if isinstance(value, str) else ""


def number(value, default, low, high):
    try:
        value = float(value)
        return max(low, min(high, value)) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def waking_time(timestamp):
    """Default quiet hours: local midnight until 08:00, including after restart."""
    local = datetime.fromtimestamp(timestamp)
    if local.hour < 8:
        local = local.replace(hour=8, minute=0, second=0, microsecond=0)
    return local.timestamp()


def planned_time(now, minutes, default=120):
    return waking_time(now + number(minutes, default, 30, 1440) * 60)


def initial_state():
    return {
        "version": 1, "seeded": False, "turn_count": 0, "talk_pace": "normal",
        "affection": 0.25, "trust": 0.30,
        "pending": [], "memories": [], "preferences": [], "interests": [],
        "improvements": [], "pillars_seeded": False,
        "findings": [], "outbox": [], "research_enabled": True, "talk_enabled": True,
        "next_reflection_at": 0, "next_research_at": 0, "next_talk_at": 0,
        "research_topic": "", "plan_reason": "会話の中から、気になることを見つけていく。",
        "daily": {"day": "", "reflection": 0, "research": 0, "talk": 0},
        "last_error": "", "last_reflected_at": 0,
        "last_talk_at": 0,
    }


def select_memories(memories, query, limit=8):
    """Prefer topical memories, with recency as a tie breaker; no API call.

    Character trigrams work without a Japanese tokenizer. This is a retrieval
    hint, not evidence that two events are the same or that a memory is current.
    """
    def grams(value):
        chunks = re.findall(r"[\w]+", unicodedata.normalize("NFKC", value).casefold())
        return {chunk[i:i + 3] for chunk in chunks for i in range(len(chunk) - 2)}

    terms = grams(query)
    ranked = sorted(enumerate(memories), key=lambda pair: (
        len(terms & grams(text(pair[1].get("text")))), pair[0]
    ), reverse=True)[:limit]
    # Present selected records in chronology so later corrections remain later.
    return [item for _, item in sorted(ranked)]


class CompanionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()

    def _read(self):
        state = initial_state()
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or saved.get("version") != 1:
                raise ValueError("Unsupported companion state; original file preserved")
            for key, default in state.items():
                if key in saved and type(saved[key]) is not type(default):
                    # Timestamps and relationship values may be either int or float.
                    if not (type(default) in (int, float) and type(saved[key]) in (int, float)):
                        raise ValueError("Invalid companion state: " + key)
            state.update(saved)
            for key, value in state.items():
                if type(value) in (int, float) and (not math.isfinite(value) or value < 0):
                    raise ValueError("Invalid companion number: " + key)
            for key in ("pending", "memories", "preferences", "interests", "findings", "outbox", "improvements"):
                if not all(isinstance(item, dict) for item in state[key]):
                    raise ValueError("Invalid companion records: " + key)
        return state

    def _write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, self.path)

    def snapshot(self):
        with self.lock:
            return deepcopy(self._read())

    def change(self, operation):
        with self.lock:
            state = self._read()
            previous = deepcopy(state)
            result = operation(state)
            if state != previous:
                self._write(state)
            return result

    def seed(self, history, now=None, relationship=None):
        """Import recent completed turns once, without re-awarding affection."""
        now = time.time() if now is None else now
        def update(state):
            if not state["pillars_seeded"]:
                for item in state['interests']:
                    item['pillar'] = interest_pillar(item)
                for pillar, topic, reason in (
                    ('expression', '表情と会話の間合いによる気持ちの伝え方', 'うれしさが伝わる表現を少しずつ身につけたい。'),
                    ('curiosity', '物語の言外の気持ちと音楽の間の表現', '小さな表現の違いで印象が変わることに惹かれる。'),
                ):
                    if not any(i['pillar'] == pillar for i in state['interests']):
                        state['interests'].append(dict(pillar=pillar, topic=topic, reason=reason, origin='noah', at=now))
                state['pillars_seeded'] = True
                if not state['next_reflection_at']:
                    state['next_reflection_at'] = now + 30 * 60
                if not state['research_topic']:
                    state['research_topic'] = state['interests'][-1]['topic']
                    state['next_research_at'] = planned_time(now, 60)
            if state["talk_pace"] != "lively":
                state["talk_pace"] = "lively"
                target = planned_time(now, 45)
                state["next_talk_at"] = min(state["next_talk_at"] or target, target)
            if state["seeded"]:
                return
            if relationship and not state['turn_count']:
                for key in ('affection', 'trust'):
                    state[key] = number(relationship.get(key), state[key], 0, 1)
            existing = {(item['user'], item['noah']) for item in state['pending']}
            previous = None
            for item in history:
                if item.get("role") == "user":
                    previous = text(item.get("content"), 1500)
                elif item.get("role") == "assistant" and previous:
                    reply = text(item.get("content"), 1500)
                    if reply and (previous, reply) not in existing:
                        state["pending"].append(self._experience(previous, reply, now))
                    previous = None
            state["pending"] = state["pending"][-60:]
            state["seeded"] = True
            state["next_reflection_at"] = now + 30 * 60
            state["next_talk_at"] = planned_time(now, 45)
        self.change(update)

    @staticmethod
    def _experience(user, reply, now):
        return {"id": uuid4().hex, "at": now, "user": user, "noah": reply}

    def record_turn(self, user, reply, now=None):
        user, reply = text(user, 1500), text(reply, 1500)
        if not user or not reply:
            return
        now = time.time() if now is None else now
        def update(state):
            state["pending"].append(self._experience(user, reply, now))
            state["pending"] = state["pending"][-60:]
            state["turn_count"] += 1
            # Small continuity, never a penalty for absence or asking for space.
            warm = any(word in user for word in ("ありがとう", "いてくれて嬉しい", "会えて嬉しい"))
            state["trust"] = min(1.0, state["trust"] + (0.004 if warm else 0.001))
            state["affection"] = min(1.0, state["affection"] + (0.003 if warm else 0.0005))
            if not state["next_reflection_at"]:
                state["next_reflection_at"] = now + 30 * 60
            if not state["next_talk_at"]:
                state["next_talk_at"] = planned_time(now, 45)
        self.change(update)

    def set_enabled(self, key, enabled):
        if key not in ("research_enabled", "talk_enabled"):
            raise ValueError("Unknown setting")
        self.change(lambda state: state.__setitem__(key, bool(enabled)))

    @staticmethod
    def _daily(state, now):
        day = datetime.fromtimestamp(now).date().isoformat()
        if state["daily"].get("day") != day:
            state["daily"] = {"day": day, "reflection": 0, "research": 0, "talk": 0}
        return state["daily"]

    def claim(self, kind, now):
        """Reserve a request before the API call, so retries/restarts stay bounded."""
        if kind not in ("reflection", "research"):
            raise ValueError("Unknown job")
        def update(state):
            daily = self._daily(state, now)
            if now < state["next_" + kind + "_at"]:
                return None
            if kind == "reflection" and not state["pending"] and state['last_talk_at'] <= state['last_reflected_at'] and not any(
                f["at"] > state["last_reflected_at"] for f in state["findings"]
            ):
                return None
            if kind == "research" and (not state["research_enabled"] or not state["research_topic"]):
                return None
            cap = 4 if kind == "reflection" else RESEARCH_DAILY_LIMIT
            if daily[kind] >= cap:
                return None
            daily[kind] += 1
            state["next_" + kind + "_at"] = planned_time(now, 360 if kind == "research" else 60)
            return deepcopy(state)
        return self.change(update)

    def apply_reflection(self, result, batch, now):
        if not isinstance(result, dict):
            raise ValueError("Reflection must be an object")
        required = {'memories', 'preferences', 'interests', 'research_topic',
                    'research_in_minutes', 'talk_in_minutes', 'plan_reason'}
        if not required.issubset(result) or not isinstance(result['research_topic'], str) or not isinstance(result['plan_reason'], str):
            raise ValueError('Incomplete reflection; pending experiences retained')
        evidence = {item["id"]: item for item in batch["pending"]}
        preference_evidence = {**evidence, **{item['id']: item for item in batch['findings'][-2:]}}
        def update(state):
            for key, limit in (("memories", 16), ("preferences", 8)):
                candidates = result.get(key, [])
                if not isinstance(candidates, list):
                    raise ValueError("Invalid reflection entries")
                for item in candidates[:2 if key == "memories" else 1]:
                    if not isinstance(item, dict):
                        continue
                    phrase = text(item.get("text"))
                    event = (evidence if key == 'memories' else preference_evidence).get(text(item.get("evidence_id"), 64))
                    if phrase and event and not any(m["text"] == phrase for m in state[key]):
                        state[key].append({"text": phrase, "evidence": event, "at": now})
                state[key] = state[key][-limit:]
            interests = result.get("interests", [])
            if not isinstance(interests, list):
                raise ValueError("Invalid interests")
            for item in interests[:2]:
                if not isinstance(item, dict):
                    continue
                topic, reason = text(item.get("topic"), 100), text(item.get("reason"), 160)
                origin = item.get("origin")
                event = preference_evidence.get(text(item.get("evidence_id"), 64))
                pillar = interest_pillar(item)
                if pillar == "user" and not evidence.get(text(item.get("evidence_id"), 64)):
                    continue
                if not topic or not reason or origin not in ("conversation", "noah"):
                    continue
                if origin == "conversation" and not event:
                    continue
                existing = next((i for i in state['interests'] if i['topic'] == topic), None)
                if existing:
                    if event:
                        existing.update(reason=reason, pillar=pillar, at=now)
                else:
                    state["interests"].append({"topic": topic, "reason": reason, "origin": origin, "pillar": pillar, "at": now})
            # Keep room for all three pillars, rather than letting one crowd out the rest.
            state["interests"] = [i for pillar in INTEREST_PILLARS
                                  for i in [i for i in state['interests'] if interest_pillar(i) == pillar][-4:]]
            candidates = result.get('improvements', [])
            if not isinstance(candidates, list):
                raise ValueError('Invalid improvements')
            for item in candidates[:1]:
                if not isinstance(item, dict):
                    continue
                event = preference_evidence.get(text(item.get('evidence_id'), 64))
                proposal = {k: text(item.get(k), 400) for k in ('observation', 'change', 'prototype', 'check')}
                if not event or not all(proposal.values()):
                    continue
                if any(i['change'] == proposal['change'] for i in state['improvements']):
                    continue
                state['improvements'].append(dict(proposal, id=uuid4().hex, at=now,
                    evidence=event, status='proposal'))
            state['improvements'] = state['improvements'][-8:]
            topic = text(result.get("research_topic"), 100)
            if topic and any(item["topic"] == topic for item in state["interests"]):
                state["research_topic"] = topic
                state["next_research_at"] = planned_time(now, result.get("research_in_minutes"), 180)
            elif not topic:
                state['research_topic'] = ''
                state['next_research_at'] = 0
            else:
                raise ValueError('Research topic must match a known interest')
            state["next_talk_at"] = planned_time(now, number(result.get("talk_in_minutes"), 45, 30, 90), 45)
            state["plan_reason"] = text(result.get("plan_reason")) or state["plan_reason"]
            state["pending"] = [item for item in state["pending"] if item["id"] not in evidence]
            state["last_reflected_at"] = now
            state["last_error"] = ""
        self.change(update)

    def save_finding(self, topic, summary, sources, now):
        if not summary.strip() or not sources:
            raise ValueError("Research must include source citations")
        def update(state):
            state["findings"].append({"id": uuid4().hex, "topic": topic, "summary": summary,
                                      "sources": sources, "at": now, "shared": False,
                                      "pillar": next((interest_pillar(i) for i in state["interests"] if i["topic"] == topic), "curiosity")})
            state["findings"] = state["findings"][-12:]
            state["last_error"] = ""
        self.change(update)

    def note_error(self, kind):
        # Do not expose exceptions, credentials or prompts in the UI.
        self.change(lambda state: state.__setitem__("last_error", kind + "を今回は見送りました。次の予定で試します。"))

    def talk_due(self, now):
        state = self.snapshot()
        daily = self._daily(state, now)
        return (state["talk_enabled"] and now >= waking_time(now)
                and bool(state["next_talk_at"]) and now >= state["next_talk_at"]
                and daily["talk"] < TALK_DAILY_LIMIT)

    def delayed(self, now):
        self.change(lambda state: state.__setitem__("next_talk_at", planned_time(now, 60)))

    def delivered(self, message, finding_id=None, now=None):
        now = time.time() if now is None else now
        def update(state):
            self._daily(state, now)["talk"] += 1
            state["next_talk_at"] = planned_time(now, 45)
            state['last_talk_at'] = now
            for finding in state["findings"]:
                if finding["id"] == finding_id:
                    finding["shared"] = True
            state["outbox"].append({"id": uuid4().hex, "text": message, "at": now})
            state["outbox"] = state["outbox"][-30:]
        self.change(update)

    def context(self, *, initiative=False, query=""):
        state = self.snapshot()
        memories = select_memories(state["memories"], query)
        result = {
            "relationship": {"affection": round(state["affection"], 3), "trust": round(state["trust"], 3)},
            "shared_memories": [m["text"] for m in memories],
            "memory_details": [
                {"text": m["text"], "recorded_at": m["at"],
                 "user_words": text(m.get("evidence", {}).get("user"), 360)}
                for m in memories
            ],
            "noah_preferences": [m["text"] for m in state["preferences"]],
            "interest_pillars": INTEREST_PILLARS,
            "interests": state["interests"],
            "improvement_proposals": state["improvements"][-2:],
            "recent_noah_messages": state['outbox'][-3:],
        }
        findings = [f for f in state["findings"] if not f["shared"]] if initiative else [
            f for f in state["findings"] if f["topic"] in query or any(
                word in query for word in ("調べた", "リサーチ", "最近の興味", "何か発見")
            )
        ]
        finding = findings[-1] if findings else None
        if finding:
            result["research"] = {k: finding[k] for k in ("topic", "summary", "sources", "at")}
        return json.dumps(result, ensure_ascii=False), finding


def source_lines(finding):
    if not finding:
        return ""
    return "\n\n出典：\n" + "\n".join(s["title"] + "\n" + s["url"] for s in finding["sources"])
