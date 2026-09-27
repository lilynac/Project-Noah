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
from .conversation_trials import TECHNIQUES, TRIAL_TURNS, active_trial, style_for_turn


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
        "learning_focus": {}, "personal_impressions": [], "improvements": [], "pillars_seeded": False, "research_threads": [],
        "conversation_trials": [], "adopted_style": "",
        "video_learning_enabled": False, "video_visual_enabled": False, "next_video_at": 0,
        "learn_conversation": True, "learn_expression": True, "learning_plan": {}, "learning_direction": {}, "learning_history": [],
        "video_candidates": [], "video_observations": [], "video_preferences": [], "video_status": "まだ調べていない。",
        "findings": [], "outbox": [], "research_enabled": True, "talk_enabled": True,
        "next_reflection_at": 0, "next_research_at": 0, "next_talk_at": 0,
        "research_topic": "", "plan_reason": "会話の中から、気になることを見つけていく。",
        "daily": {"day": "", "reflection": 0, "research": 0, "talk": 0},
        "last_error": "", "last_reflected_at": 0, "last_quality": {},
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
            for key in ("pending", "memories", "preferences", "interests", "findings", "outbox", "improvements", "research_threads", "conversation_trials", "video_candidates", "video_observations", "video_preferences", "learning_history", "personal_impressions"):
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

    def record_turn(self, user, reply, now=None, *, trial_id=None):
        user, reply = text(user, 1500), text(reply, 1500)
        if not user or not reply:
            return
        now = time.time() if now is None else now
        def update(state):
            state["pending"].append(self._experience(user, reply, now))
            state["pending"] = state["pending"][-60:]
            state["turn_count"] += 1
            trial = active_trial(state)
            if trial and trial['id'] == trial_id:
                trial['samples'].append({'user': user, 'reply': reply, 'at': now})
                if len(trial['samples']) >= TRIAL_TURNS:
                    trial['status'] = 'awaiting_feedback'
                    trial['ended_at'] = now
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
        if key not in ("research_enabled", "talk_enabled", "video_learning_enabled", "video_visual_enabled", "learn_conversation", "learn_expression"):
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
        if kind not in ("reflection", "research", "video"):
            raise ValueError("Unknown job")
        def update(state):
            daily = self._daily(state, now)
            if now < state["next_" + kind + "_at"]:
                return None
            if kind == "reflection" and not state["pending"] and state['last_talk_at'] <= state['last_reflected_at'] and not any(
                f["at"] > state["last_reflected_at"] for f in state["findings"] + state["video_observations"]
            ):
                return None
            if kind == "research" and (not state["research_enabled"] or not state["research_topic"]):
                return None
            if kind == 'video' and (not state['video_learning_enabled'] or not (state['learn_conversation'] or state['learn_expression'])):
                return None
            cap = 4 if kind == "reflection" else RESEARCH_DAILY_LIMIT
            if daily.get(kind, 0) >= cap:
                return None
            daily[kind] = daily.get(kind, 0) + 1
            state["next_" + kind + "_at"] = planned_time(now, 360 if kind in ('research', 'video') else 60)
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
            from .personal_discoveries import retain_impressions
            retain_impressions(state, result, batch, now)
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
                    evidence=event, status='proposal',
                    technique=item.get('technique') if item.get('technique') in TECHNIQUES else ''))
            state['improvements'] = state['improvements'][-8:]
            self._start_conversation_trial(state, now)
            updates = result.get('explorations', [])
            if not isinstance(updates, list):
                raise ValueError('Invalid explorations')
            eligible = {f['id']: f for f in batch['findings'][-2:]}
            for item in updates[:2]:
                if not isinstance(item, dict) or item.get('finding_id') not in eligible:
                    continue
                finding = eligible[item['finding_id']]
                values = {key: text(item.get(key), 400) for key in ('learned', 'open_question', 'next_reading', 'changed_view')}
                if not values['learned'] or not values['open_question'] or not values['next_reading']:
                    continue
                for trail in state['research_threads']:
                    for step in trail['steps']:
                        if step['finding_id'] == finding['id']:
                            # A reflection annotates a finding once, preserving its history.
                            if 'learned' not in step:
                                step.update(values)
            direction = result.get('learning_direction', {})
            from .learning_plan import valid_direction
            if valid_direction(direction):
                state['learning_direction'] = {k: direction[k] for k in ('goal', 'method')}
                for key in ('question', 'reason', 'check'):
                    if text(direction.get(key), 250):
                        state['learning_direction'][key] = text(direction.get(key), 250)
            topic = text(result.get("research_topic"), 100)
            if topic and any(item["topic"] == topic for item in state["interests"]):
                state["research_topic"] = topic
                state["next_research_at"] = planned_time(now, result.get("research_in_minutes"), 180)
            elif not topic:
                state['research_topic'] = ''
                state['next_research_at'] = 0
            else:
                raise ValueError('Research topic must match a known interest')
            target = planned_time(now, number(result.get("talk_in_minutes"), 45, 30, 90), 45)
            state["next_talk_at"] = min(state["next_talk_at"] or target, target)
            state["plan_reason"] = text(result.get("plan_reason")) or state["plan_reason"]
            state["pending"] = [item for item in state["pending"] if item["id"] not in evidence]
            state["last_reflected_at"] = now
            state["last_error"] = ""
        self.change(update)

    def conversation_style(self):
        return style_for_turn(self.snapshot())

    @staticmethod
    def _start_conversation_trial(state, now):
        if not any(t['status'] in ('active', 'awaiting_feedback') for t in state['conversation_trials']):
            tried = {t['proposal']['id'] for t in state['conversation_trials']}
            declined = {t['technique'] for t in state['conversation_trials']
                        if t['status'] in ('stopped', 'inconclusive')}
            candidate = next((p for p in reversed(state['improvements'])
                              if p.get('technique') in TECHNIQUES and p['id'] not in tried
                              and p['technique'] not in declined
                              and p['technique'] != state['adopted_style']), None)
            if candidate:
                before = state['pending'][-1] if state['pending'] else None
                state['conversation_trials'].append({'id': uuid4().hex, 'proposal': deepcopy(candidate),
                    'technique': candidate['technique'], 'status': 'active', 'started_at': now,
                    'samples': [], 'before': deepcopy(before), 'feedback': ''})
                state['conversation_trials'] = state['conversation_trials'][-12:]

    def evaluate_trial(self, trial_id, verdict, now=None):
        if verdict not in ('adopted', 'stopped', 'inconclusive'):
            raise ValueError('Unknown trial evaluation')
        now = time.time() if now is None else now
        def update(state):
            trial = next((t for t in state['conversation_trials'] if t['id'] == trial_id), None)
            if not trial or trial['status'] not in ('active', 'awaiting_feedback'):
                raise ValueError('Trial is no longer awaiting evaluation')
            if verdict == 'adopted' and not trial['samples']:
                raise ValueError('Try at least one reply before adoption')
            trial.update(status=verdict, feedback=verdict, ended_at=now)
            if verdict == 'adopted':
                state['adopted_style'] = trial['technique']
        self.change(update)

    def note_video_status(self, message):
        self.change(lambda state: state.update(video_status=text(message, 240)))

    def save_video_candidate(self, candidate, status, now, note=None):
        from .video_learning import canonical_video
        url = canonical_video(candidate['url'])
        if not url:
            raise ValueError('Invalid video URL')
        def update(state):
            record = next((v for v in state['video_candidates'] if v['url'] == url), None)
            if record is None:
                record = {'url': url, 'title': text(candidate['title'], 160)}
                state['video_candidates'].append(record)
            record.update(status=status, at=now)
            state['video_candidates'] = state['video_candidates'][-120:]
            state['video_status'] = status
            if not note or any(o['url'] == url for o in state['video_observations']):
                return
            observation = dict(deepcopy(note), id=uuid4().hex, url=url, title=record['title'], at=now)
            state['video_observations'].append(observation)
            state['video_observations'] = state['video_observations'][-40:]
            if not note.get('preference') or note.get('technique') not in TECHNIQUES:
                return
            proposal = {'id': observation['id'], 'at': now, 'status': 'proposal', 'source_kind': 'caption_observation',
                'observation': note['observation'], 'change': TECHNIQUES[note['technique']]['label'],
                'prototype': note['prototype'], 'check': note['use_when'] + ' ／ 避ける場面：' + note['avoid_when'],
                'technique': note['technique'], 'evidence': {'id': observation['id'],
                    'summary': note['access'] + '\n' + note['observation'],
                    'sources': [{'title': record['title'], 'url': url + '&t=' + str(int(note['at_seconds']))}]}}
            state['improvements'].append(proposal)
            state['improvements'] = state['improvements'][-8:]
            self._start_conversation_trial(state, now)
        self.change(update)

    def reset_adopted_style(self):
        self.change(lambda state: state.update(adopted_style=''))

    def save_video_visual(self, observation_id, status, visual, now):
        def update(state):
            note = next((n for n in state['video_observations'] if n['id'] == observation_id), None)
            if note is None:
                return
            note.update(visual_status=text(status, 160), visual_at=now)
            if visual:
                note['visual'] = deepcopy(visual)
        self.change(update)

    def research_history(self, topic):
        """Only public research records, never conversation or profile data."""
        state = self.snapshot()
        return research_history(state, topic)

    def save_finding(self, topic, summary, sources, now):
        if not summary.strip() or not sources:
            raise ValueError("Research must include source citations")
        def update(state):
            finding_id = uuid4().hex
            state["findings"].append({"id": finding_id, "topic": topic, "summary": summary,
                                      "sources": sources, "at": now, "shared": False,
                                      "pillar": next((interest_pillar(i) for i in state["interests"] if i["topic"] == topic), "curiosity")})
            state["findings"] = state["findings"][-12:]
            trail = next((t for t in state['research_threads'] if t['topic'] == topic), None)
            if trail is None:
                trail = {'topic': topic, 'steps': [
                    {'finding_id': f['id'], 'at': f['at'], 'summary': f['summary'], 'sources': deepcopy(f['sources'])}
                    for f in state['findings'][:-1] if f['topic'] == topic][-3:]}
            else:
                state['research_threads'].remove(trail)
            trail['steps'].append({'finding_id': finding_id, 'at': now, 'summary': summary,
                                   'sources': deepcopy(sources)})
            trail['steps'] = trail['steps'][-4:]
            state['research_threads'].append(trail)
            state['research_threads'] = state['research_threads'][-12:]
            state["last_error"] = ""
        self.change(update)

    def record_quality(self, reason, now):
        from .initiative.quality import QUALITY_LABELS
        if reason not in QUALITY_LABELS:
            raise ValueError('Unknown quality result')
        self.change(lambda state: state.update(last_quality={'reason': reason, 'at': now}))

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
            for finding in state["findings"] + state["video_observations"]:
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
            "learning_focus": state["learning_focus"],
            "personal_impressions": state["personal_impressions"][-5:],
            "noah_preferences": [m["text"] for m in state["preferences"]],
            "interest_pillars": INTEREST_PILLARS,
            "interests": state["interests"],
            "improvement_proposals": state["improvements"][-2:],
            "recent_noah_messages": state['outbox'][-3:],
        }
        if initiative or any(word in query for word in ('字幕', '動画', '学ん', '会話の工夫')):
            result['caption_learning'] = {
                'status': state['video_status'], 'access': '資料ごとのaccessを参照。静止画は動画全編の視聴・音声の確認ではない。',
                'observations': [{k: note[k] for k in ('title', 'url', 'at', 'at_seconds', 'observation', 'prototype', 'access', 'visual', 'visual_status') if k in note}
                                 for note in state['video_observations'][-2:]]}
        findings = [f for f in state["findings"] if not f["shared"]] if initiative else [
            f for f in state["findings"] if f["topic"] in query
            or ("月ノ美兎" in query and "月ノ美兎" in f["topic"]) or any(
                word in query for word in ("調べた", "リサーチ", "最近の興味", "何か発見")
            )
        ]
        if initiative:
            findings += [dict(id=n['id'], topic=n['title'],
                             summary=n['observation'] + '\n確認範囲：' + n['access'],
                             sources=[{'title': n['title'], 'url': n['url'] + '&t=' + str(int(n['at_seconds']))}], at=n['at'])
                         for n in state['video_observations'] if not n.get('shared')]
        finding = max(findings, key=lambda f: f['at']) if findings else None
        if finding:
            result["research"] = {k: finding[k] for k in ("topic", "summary", "sources", "at")}
            result['research_progress'] = research_history(state, finding['topic'])
        return json.dumps(result, ensure_ascii=False), finding


def source_lines(finding):
    if not finding:
        return ""
    return "\n\n出典：\n" + "\n".join(s["title"] + "\n" + s["url"] for s in finding["sources"])


def research_history(state, topic):
    trail = next((t for t in state.get('research_threads', []) if t['topic'] == topic), None)
    if trail:
        records = trail['steps'][-3:]
    else:
        # Older stores have findings but no trails yet. Read without rewriting them.
        records = [f for f in state['findings'] if f['topic'] == topic][-3:]
    fields = ('at', 'summary', 'sources', 'learned', 'open_question', 'next_reading', 'changed_view')
    return [{key: (text(r[key], 1600) if isinstance(r[key], str) else deepcopy(r[key]))
             for key in fields if key in r} for r in records]
