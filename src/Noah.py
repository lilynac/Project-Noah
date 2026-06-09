# =========================
# Standard library imports
# =========================
import argparse
import hashlib
import json
import logging
import os
import random
import re
import signal
import subprocess
import time
import traceback
import unicodedata
import sys as _sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock, Thread

# =========================
# Third-party imports
# =========================
from dotenv import load_dotenv
from openai import OpenAI

# =========================
# Project imports (src / local)
# =========================
from src.retrieve import get_entity_brief, format_brief_for_prompt
from src.initiative.generation import generate_initiative_text

from .db import connect
from .noah_config import load_runtime_config, RuntimeConfig
from .log_setup import get_logger, ensure_pid_lock_or_exit, cleanup_pid_lock

from .emotional_update import update_emotional_marks
from .noah_identity_update import update_noah_identity
from .preferences_update import update_preferences
from .noah_research_update import update_noah_research
from .noah_research_promote import promote_research_topics
from .affection_update import update_affection_state
from src.initiative.context import read_last_research_block, extract_research_phrase, should_inject_research
from src.initiative.context import build_research_phrase
from src.memory.decay import apply_decay
from src.memory.retrieve import retrieve_memories, format_memory_block
from src.memory.decay import reinforce

from .paths import (
    MEMORY_DIR,
    CONSULTS_PATH,
    PREFERENCES_PATH,
    EMOTIONAL_MARKS_PATH,
    NOAH_IDENTITY_PATH,
    NOAH_STATE_PATH,
    MODE_PATH,
    UI_QUEUE_PATH,
    NOAH_RESEARCH_PATH,
    RESEARCH_USAGE_LOG_PATH,
    RESEARCH_PROMOTED_PATH,
    SUPPRESSION_PATH,
    RUNTIME_STATE_PATH,
)


from .suppression import (
    _sup_load,
    _sup_save,
    _sup_detect,
    _sup_update,
    _sup_is_suppressed,
    _sup_system_prompt,
)

# =========================
# Module aliasing
# =========================
_this = _sys.modules.get(__name__)
if _this is not None:
    # よくある別名を同一実体に揃える
    _sys.modules.setdefault("Noah", _this)
    if __package__:
        _sys.modules.setdefault(f"{__package__}.Noah", _this)

# =========================
# Optional imports
# =========================
try:
    from src.initiative.signals import (
        load_signals,
        save_signals,
        touch_user_message,
        touch_noah_message,
        set_mode,
    )
    from src.initiative.decision import DecisionEngine
except Exception:
    load_signals = None
    save_signals = None
    touch_user_message = None
    touch_noah_message = None
    set_mode = None
    DecisionEngine = None


from .noah_prompts import SYSTEM_CORE_PROMPT, SYSTEM_DELEGATED_MODE_PROMPT
from .llm_trace import (
    configure_trace,
    trace_llm,
    _prune_trace_file_keep_last_turns,
    _llm_in_pretty,
    _safe_preview,
    _hash_text,
    _hash_short,
    _TRACE_LOCK,
)
from .conversation_history import (
    configure_conversation_history,
    CONVERSATION_HISTORY,
    CONVERSATION_MAX_TURNS,
    _conversation_lock,
    load_conversation_history,
    persist_conversation_history,
    _recent_turn_texts,
)

# =========================
# 初期設定
# =========================
# D4: config/.env を優先して読む（無ければ通常の .env）
_env_candidates = [Path(__file__).resolve().parent / "config" / ".env", Path(".env")]
for _p in _env_candidates:
    if _p.exists():
        load_dotenv(dotenv_path=str(_p))
        break
else:
    load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY")
try:
    client = OpenAI(api_key=_api_key) if _api_key else None
except Exception as e:
    client = None
    try:
        get_logger().warning(f"OPENAI_CLIENT_INIT_FAILED: {e}")
    except Exception:
        print(f"[WARN] OPENAI_CLIENT_INIT_FAILED: {e}")

CFG: RuntimeConfig = load_runtime_config(base_dir=Path(__file__).resolve().parents[1])

INTERNAL_NAME = "あなた"
NOAH_NAME = "Noah"

EMOTIONAL_UPDATE_INTERVAL = 10 * 60          # 10分
NOAH_IDENTITY_UPDATE_INTERVAL = 60 * 60      # 60分
TRACE_MAX_TURNS = 20
_TRACE_TURN_ID = 0
configure_trace(log_dir=CFG.log_dir, max_turns=TRACE_MAX_TURNS)

DEBUG_INJECTION = False
DEBUG_INITIATIVE_LOOP = False

# =========================
# 自発会話（Initiative）設定
# =========================
INITIATIVE_PER_HOUR = CFG.initiative_per_hour
INITIATIVE_BASE_INTERVAL = int(60 * 60 / max(1, INITIATIVE_PER_HOUR))
INITIATIVE_JITTER = CFG.initiative_jitter_seconds                   # ±jitter
INITIATIVE_MIN_GAP = CFG.initiative_min_gap_seconds
INITIATIVE_RECENT_USER_SILENCE = CFG.initiative_recent_user_silence_seconds
INITIATIVE_MUTE_SECONDS = CFG.initiative_mute_seconds            # stop signal で自発会話をミュート
INITIATIVE_CONVERSATION_BLOCK = CFG.initiative_conversation_block_seconds
AFFECTION_UPDATE_INTERVAL = 10 * 60  # 10分

# =========================
# Runtime State（実行時状態）
# =========================
_state_lock = Lock()

_last_user_at: float = 0.0
_last_noah_initiative_at: float = 0.0
_initiative_count: int = 0

_startup_research_used: bool = False
_last_research_injected_date = None
_research_injected_today: int = 0

_initiative_muted_until: float = 0.0         # epoch seconds

_last_initiative_text: str = ""
_last_initiative_hash: str = ""
_initiative_state_last: str = "" 

# =========================
# Utilities / I-O
# =========================
_logger = None

def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _logger = get_logger(
        component="noah",
        log_dir=CFG.log_dir,
        level=CFG.log_level,
        max_bytes=CFG.log_max_bytes,
        backup_count=CFG.log_backup_count,
    )
    _logger.info("NOAH_LOGGER_READY log_dir=%s abs=%s", str(CFG.log_dir), str(CFG.log_dir.resolve()))
    return _logger





def log_error(kind: str, err: Exception, context: dict | None = None) -> None:
    try:
        logger = _get_logger()
        ctx = dict(context or {})

        # user_input を入れる場合は preview + hash だけにする
        if "user_input" in ctx:
            ui = str(ctx.get("user_input") or "")
            ctx["user_input_preview"] = _safe_preview(ui)
            ctx["user_input_hash"] = _hash_text(ui)
            del ctx["user_input"]

        msg = f"[{kind}] {type(err).__name__}: {err} | ctx={ctx}"
        logger.error(msg)
        logger.error(traceback.format_exc())
    except Exception:
        # ログで落ちるのが最悪なので握る
        return

configure_conversation_history(memory_dir=MEMORY_DIR, error_logger=log_error, max_turns=CONVERSATION_MAX_TURNS)
    

def log_initiative_gate(now: float, reason: str, text: str = "") -> None:
    try:
        with _state_lock:
            last_user = _last_user_at
            last_noah = _last_noah_initiative_at
            muted_until = _initiative_muted_until

            # D2ブロックで定義している _ipc_in_flight を参照（無い場合は0）
            ipc = 0
            try:
                ipc = int(_ipc_in_flight)
            except Exception:
                ipc = 0

        mute_remaining = max(0, int((muted_until or 0.0) - now))
        since_user = int(now - (last_user or 0.0))
        since_noah = int(now - (last_noah or 0.0))

        # 文章のhash（重複確認用）
        try:
            t = normalize_input(text or "")
        except Exception:
            t = (text or "").strip()
        text_hash = _hash_text(t)

        logger = _get_logger()
        logger.info(
            "INITIATIVE_GATE "
            f"now={now:.3f} "
            f"reason={reason} "
            f"mute_remaining_sec={mute_remaining} "
            f"ipc_in_flight={ipc} "
            f"since_user_sec={since_user} "
            f"since_noah_sec={since_noah} "
            f"text_hash={text_hash}"
        )
    except Exception as e:
        # ログ用関数が原因で落ちないようにする
        log_error("INITIATIVE_GATE_LOG", e, {"reason": reason})











def _pick_entity_from_text(user_input: str) -> str | None:
    """
    user_input に含まれる entity/alias をDBから探して、最も長く一致したものを返す。
    （誤爆防止で最大1件）
    """
    text = user_input or ""
    if not text:
        return None

    con = connect()  # すでにNoah.pyで connect を使ってるならそれを利用
    try:
        # canonical + alias をまとめて候補化
        rows = con.execute("""
            SELECT e.canonical_name AS name
            FROM entities e
            UNION
            SELECT a.alias AS name
            FROM entity_aliases a
        """).fetchall()

        # 最長一致を選ぶ
        hits = []
        for r in rows:
            name = r[0]
            if name and name in text:
                hits.append(name)

        if not hits:
            return None

        # 一番長い（具体的）名前を採用
        hits.sort(key=len, reverse=True)
        return hits[0]
    finally:
        con.close()



# =========================
# Initiative Gate / State
# =========================
from collections import deque

# IPCで会話が「処理中」かどうか（in-flight）
_ipc_in_flight: int = 0

# 直近重複禁止（直前1件→直近N件に強化）
_recent_initiative_hashes = deque(maxlen=12)  # 直近12件ぶんのhashを保持

def ipc_begin() -> None:
    global _ipc_in_flight
    with _state_lock:
        _ipc_in_flight += 1

def ipc_end() -> None:
    global _ipc_in_flight
    with _state_lock:
        _ipc_in_flight = max(0, _ipc_in_flight - 1)

def note_user_activity() -> None:
    global _last_user_at
    with _state_lock:
        _last_user_at = time.time()

def set_initiative_state(state: str, reason: str = "") -> None:
    global _initiative_state_last
    try:
        if state == _initiative_state_last:
            return
        _initiative_state_last = state
        payload = f"{state}\t{reason}".strip()
        ui_emit("INITIATIVE_STATE", payload, emotion="idle")
    except Exception as e:
        log_error("INITIATIVE_STATE", e, {"state": state, "reason": reason})

def mute_initiative(seconds: int, reason: str = "stop_signal") -> None:
    global _initiative_muted_until
    try:
        with _state_lock:
            _initiative_muted_until = time.time() + seconds
        set_initiative_state("OFF", f"muted:{reason}")
    except Exception as e:
        log_error("MUTE_INITIATIVE", e, {"seconds": seconds, "reason": reason})
    
    logger = _get_logger()
    logger.info(f"MUTE_SET now={time.time():.3f} muted_until={_initiative_muted_until:.3f} reason={reason}")


def should_fire_initiative(now: float) -> tuple[bool, str]:
    # --- D4 suppression gate: 抑制中は発火させない ---
    try:
        sup = _sup_load(SUPPRESSION_PATH)
        if _sup_is_suppressed(sup):
            _get_logger().info("SUPPRESSION_STATE ns=dialogue persistent=True path=legacy_gate")
            return False, "suppressed"

    except Exception:
        pass

    with _state_lock:
        last_user = _last_user_at
        last_noah = _last_noah_initiative_at
        muted_until = _initiative_muted_until
        ipc_busy = (_ipc_in_flight > 0)

    # ① stop/静かに のクールダウン最優先
    if now < muted_until:
        return False, "muted"

    # ② IPCで会話が進行中（処理中）なら絶対に発火しない
    if ipc_busy:
        return False, "ipc_busy"

    # ③ 最低間隔
    if now - last_noah < INITIATIVE_MIN_GAP:
        return False, "min_gap"

    # ④ 会話中は発火しない（直近のユーザー発話から一定時間）
    if now - last_user < INITIATIVE_CONVERSATION_BLOCK:
        return False, "conversation_active"

    # ⑤ 既存の短い割り込み禁止も保持
    if now - last_user < INITIATIVE_RECENT_USER_SILENCE:
        return False, "recent_user"

    # ⑥ workモードは控えめに
    try:
        work = is_work_mode()
    except Exception:
        work = False
    if work and random.random() < 0.5:
        return False, "work_mode_skip"

    return True, "ok"

def _initiative_is_duplicate(text: str) -> bool:
    h = _hash_short(text)
    return h in _recent_initiative_hashes

def _initiative_register(text: str) -> None:
    h = _hash_short(text)
    _recent_initiative_hashes.append(h)

def allow_and_register_initiative(text: str) -> tuple[bool, str]:
    now = time.time()

    ok, reason = should_fire_initiative(now)
    if not ok:
        log_initiative_gate(now, reason, text)
        return False, reason

    if _initiative_is_duplicate(text):
        log_initiative_gate(now, "duplicate", text)
        return False, "duplicate"

    _initiative_register(text)
    log_initiative_gate(now, "ok", text)
    return True, "ok"


def emit_initiative(text: str) -> bool:
    logger = _get_logger()
    text_hash = _hash_short(text)
    logger.info(f"EMIT_TRY now={time.time():.3f} text_hash={text_hash}")

    ok, reason = allow_and_register_initiative(text)
    if not ok:
        logger.info(f"INITIATIVE_EMIT_SKIP reason={reason} text_hash={text_hash}")
        set_initiative_state("OFF", reason)
        return False

    save_log("(initiative)", text)
    logger.info(f"INITIATIVE_EMIT_SAVE_LOG_DONE text_hash={text_hash}")

    ui_emit("SAY", text, emotion="idle")
    logger.info("INITIATIVE_EMIT_TEXT text=%r", text)
    print(f"[Initiative] {text}", flush=True)

    logger.info(f"INITIATIVE_EMIT_DONE text_hash={text_hash}")
    return True


def detect_user_wants_examples(text: str) -> bool:
    t = (text or "")
    triggers = ["いくつか", "挙げて", "あげて", "例を", "おすすめ", "候補", "まずはNoah", "まずは"]
    # 条件指定（＝次も候補を出すべき）
    condition = ["激しい", "疾走感", "盛り上がる", "テンション", "速い", "ドラム", "ロック", "EDM", "メタル", "パンク"]
    return any(w in t for w in triggers) or any(w in t for w in condition)



def detect_stop_signal(text: str) -> bool:
    t = normalize_input(text)
    if not t:
        return False
    stop_words = [
        "やめて", "やめよう", "黙っ", "いまはいい", "今はいい", "放っておいて",
        "しんどい", "また今度", "後で", "今日はやめたい","静かに"
    ]
    return any(w in t for w in stop_words)


def detect_delegation(text: str) -> bool:
    t = (text or "")
    triggers = ["決めて", "決めてほしい", "従う", "任せる", "考えたくない", "判断して", "選んで"]
    return any(w in t for w in triggers)


def detect_action_request(text: str) -> bool:
    """
    行動質問（接し方・対応・返信・方針・距離感など）っぽい入力を検出する。
    目的: Trueのときだけ「スタンス＋具体2点」フォーマット強制を付与するため。

    ねらい:
      - 「どう接する/どう対応/どう返す/スタンス/方針/距離感/線引き/断り方/返信」などは強いシグナル
      - 「どう思う/解釈/感想/意味」など“分析寄り”は誤爆しやすいので抑制
      - 短すぎる曖昧入力はFalseに倒す（例:「どうする？」だけ）
    """
    if not text:
        return False

    t = text.strip()
    if not t:
        return False

    # ざっくり正規化（全角スペース/改行/タブなどを1個の空白に）
    t_norm = re.sub(r"\s+", " ", t)

    # ---- 強い行動系トリガー（Trueになりやすい） ----
    strong_triggers = (
        "どう接する", "どう対応", "どう返す", "どう言う", "どう言えば", "どう伝える",
        "どう振る舞う", "どうするべき", "どうすべき", "どうしたら",
        "接し方", "対応方針", "方針", "スタンス", "距離感", "線引き",
        "断り方", "謝り方", "頼み方", "言い方",
        "返信", "返事", "連絡", "誘い", "断る",
        "会ったら", "会うとき", "次に", "これから",
    )

    # ---- 弱い行動系シグナル（単体だと誤爆するので補助） ----
    weak_signals = (
        "したい", "したくない", "すべき", "したほうが", "やったほうが", "避けたい",
        "やめたい", "続けたい", "迷う", "困る",
    )

    # ---- 非行動（分析/感想/意味）寄りの抑制ワード ----
    non_action = (
        "どう思う", "どう感じる", "意味", "解釈", "感想", "評価",
        "心理", "気持ち", "性格", "特徴", "なぜ", "理由",
    )

    hit_strong = any(w in t_norm for w in strong_triggers)
    hit_weak = any(w in t_norm for w in weak_signals)
    hit_non = any(w in t_norm for w in non_action)

    # ---- 末尾が質問っぽいか（日本語） ----
    looks_like_question = bool(re.search(r"(？|\?|ですか|ますか|かな|かね|か)$", t_norm))

    # ---- 短すぎる入力は誤爆しやすいのでFalse寄り ----
    too_short = len(t_norm) < 8  # 「どうする？」等を落とす

    # ---- 判定ロジック ----
    # 1) 強トリガーがあれば基本True。ただし分析寄りが強い場合は落とす
    if hit_strong:
        if hit_non and not hit_weak:
            return False
        # 短すぎるなら追加条件が欲しい（weak or 質問形式 or 具体語）
        if too_short and not (hit_weak or looks_like_question):
            return False
        return True

    # 2) 強トリガーがない場合は、弱シグナル + 質問形式が揃ったときだけTrue
    if hit_weak and looks_like_question and not hit_non and not too_short:
        return True

    return False


def detect_question_complaint(text: str) -> bool:
    t = (text or "")
    triggers = [
        "質問ばっか", "質問ばか", "質問多い", "しつこい", "ワンパターン",
        "何度も言わないで", "言わないで", "もう聞かないで", "繰り返さないで",
        "気になっていることはありますかと言わないで",
    ]
    return any(w in t for w in triggers)


def normalize_input(text: str) -> str:
    t = unicodedata.normalize("NFKC", (text or ""))
    t = " ".join(t.strip().split())
    return t


def safe_read(path, tail: bool = False, lines: int = 5) -> str:
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if tail:
            blocks = content.split("\n\n")
            return "\n\n".join(blocks[-lines:])
        return content
    except Exception as e:
        log_error("SAFE_READ", e, {"path": path})
        return ""


def load_state_snippet() -> str:
    state = safe_read(NOAH_STATE_PATH)
    return state.strip()[:420]


def speak_mac(text: str, rate: int = 185):
    t = " ".join((text or "").split()).strip()
    if not t:
        return
    try:
        subprocess.run(["say", "-r", str(rate), t], check=False)
    except Exception:
        pass


def ui_emit(event_type: str, payload: str = "", emotion: str = "idle"):
    """
    UI連携：1行=1イベントの超軽量プロトコル
    形式: TYPE\tEMOTION\tPAYLOAD
    例: SAY\tsoft_smile\tこんにちは
    """
    try:
        os.makedirs(os.path.dirname(UI_QUEUE_PATH), exist_ok=True)
        line = f"{event_type}\t{emotion}\t{payload}".replace("\n", " ").strip()
        with open(UI_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        log_error("UI_EMIT", e, {"path": UI_QUEUE_PATH, "event_type": event_type})
        return


def save_log(user_text: str, noah_text: str):
    from src.memory.store import store_episode
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        SESSION_TAG = "v2"
        log = (
            f"[{timestamp}] @{SESSION_TAG}\n"
            f"{INTERNAL_NAME}: {user_text}\n"
            f"{NOAH_NAME}: {noah_text}\n\n"
        )
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with open(CONSULTS_PATH, "a", encoding="utf-8") as f:
            f.write(log)

        # ---- Task3: store episode memories (fast, rule-based) ----
        try:
            store_episode(user_text, source="user")
            store_episode(noah_text, source="noah")
        except Exception as e:
            log_error("STORE_EPISODE", e, {})

    except Exception as e:
        log_error("SAVE_LOG", e, {"path": CONSULTS_PATH})
        return


def log_research_usage(source: str, used: bool):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        status = "USED" if used else "SKIPPED"
        line = f"[{ts}] {source} {status}\n"
        os.makedirs(os.path.dirname(RESEARCH_USAGE_LOG_PATH), exist_ok=True)
        with open(RESEARCH_USAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        log_error("RESEARCH_USAGE_LOG", e, {"path": RESEARCH_USAGE_LOG_PATH})
        return


# =========================
# Core Logic
# =========================
def build_messages(user_input: str):
    from . import message_builder as _message_builder
    return _message_builder.build_messages(user_input, globals())



def _wants_short_reply(text: str) -> bool:
    triggers = ["短く", "コンパクト", "要点", "簡潔", "長い", "短め", "手短に"]
    return any(t in (text or "") for t in triggers)


def is_work_mode() -> bool:
    mode = safe_read(MODE_PATH)
    return "mode: work" in mode


def load_context() -> str:
    recent_emotional = safe_read(EMOTIONAL_MARKS_PATH, tail=True, lines=5)
    preferences = safe_read(PREFERENCES_PATH)
    identity = safe_read(NOAH_IDENTITY_PATH, tail=True, lines=10)
    mode = safe_read(MODE_PATH)
    promoted = safe_read(RESEARCH_PROMOTED_PATH, tail=True, lines=3)

    context_parts = []
    if mode.strip():
        context_parts.append(mode.strip())
    if recent_emotional.strip():
        context_parts.append(recent_emotional.strip())
    if preferences.strip():
        context_parts.append(preferences.strip())
    if identity.strip():
        context_parts.append(identity.strip())
    if promoted.strip():
        context_parts.append(promoted.strip())

    return "\n\n".join(context_parts).strip()


def generate_reply(user_input: str) -> str:
    global _TRACE_TURN_ID
    _TRACE_TURN_ID += 1
    turn_id = _TRACE_TURN_ID

    messages = build_messages(user_input)


    # ---- Task3: memory retrieve (3-level) ----
    mem = {}
    mem_block = ""
    try:
        mem = retrieve_memories(user_input, top_narrative=2, top_summary=4, top_episode=3)
        mem_block = format_memory_block(mem)
    except Exception as e:
        log_error("MEMORY_RETRIEVE", e, {})

    if mem_block:
        mem_block = mem_block[:1200]

    if mem_block:
        # build_messages() が system を先頭に置いている想定。
        # system が無い場合でも安全に動くように fallback する
        inserted = False
        for m in messages:
            if m.get("role") == "system":
                m["content"] += "\n\n[MEMORY]\n" + mem_block
                inserted = True
                break
        if not inserted:
            messages.insert(0, {"role": "system", "content": "[MEMORY]\n" + mem_block})


    short_mode = _wants_short_reply(user_input)
    if short_mode:
        for m in messages:
            if m.get("role") == "system":
                m["content"] += "\n\n返答は短く、要点だけ。長い説明はしない。"
                break
        else:
            messages.insert(0, {"role": "system", "content": "返答は短く、要点だけ。長い説明はしない。"})

    max_tokens = 120 if short_mode else 350
    temperature = 0.4
    model_name = "gpt-4o-mini"

    trace_llm("LLM_IN", {
        "turn_id": turn_id,
        "model": model_name,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "pretty": _llm_in_pretty(messages),
        # rawを残す運用なら↓（容量が気になるなら消してOK）
        "messages": messages,
    })

    try:
        response = client.responses.create(
            model=model_name,
            input=messages,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
    except Exception as e:
        trace_llm("LLM_ERR", {
            "turn_id": turn_id,
            "phase": "responses.create",
            "err": repr(e),
            "user_input_preview": _safe_preview(user_input),
            "user_input_hash": _hash_text(user_input),
        })

        # ここで prune（エラーでも古いログを落とす）
        with _TRACE_LOCK:
            _prune_trace_file_keep_last_turns(turn_id)

        # ---- reinforce（副作用フェーズ）----
        try:
            ids = mem.get("reinforce_ids", {})

            for mid in ids.get("narrative", []):
                reinforce("narrative", mid, 0.03)

            for mid in ids.get("summary", []):
                reinforce("summary", mid, 0.05)

            for mid in ids.get("episode", []):
                reinforce("episode", mid, 0.08)

        except Exception as e:
            log_error("MEMORY_REINFORCE", e, {})

        log_error("API", e, {"phase": "responses.create", "user_input": user_input})
        return "……今ちょっと不安定みたい。ここで受け止める。"

    reply = getattr(response, "output_text", None) or ""
    if not reply:
        try:
            parts = []
            for item in getattr(response, "output", []) or []:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        parts.append(getattr(c, "text", ""))
            reply = "".join(parts).strip()
        except Exception:
            reply = ""

    if not reply:
        reply = "……うまく言葉が出てこない。言葉が増えるまで、ここで受け止める。"

    trace_llm("LLM_OUT", {
        "turn_id": turn_id,
        "reply": reply,
        "reply_len": len(reply),
    })

    # OUTのあと prune（正常時）
    with _TRACE_LOCK:
        _prune_trace_file_keep_last_turns(turn_id)

    # ---- Affective output: テンプレ合成はしない ----
    # LLMが、蓄積された状態・記憶・直近文脈をもとに生成した言葉をそのまま返す。
    # ここで固定フレーズを足すとロボット感が出るため、後段合成は禁止。

    # （以下、履歴保存など既存処理…）
    return reply


# DEPRECATED (initiative generation):
# - initiative_loop からは呼ばないこと（src/initiative/generation.generate_initiative_text が唯一の生成経路）
# - Noah.py に生成ルール（質問許可など）を再導入しないための封印
# - もし LLM 生成が必要になったら src/initiative 側に移設し、同一制約（疑問文禁止など）を共有する


def generate_initiative() -> str:
    global _initiative_count, _research_injected_today, _last_research_injected_date

    # ===== research（余韻） =====
    research_phrase = ""
    used_research = False

    today = datetime.now().date()

    ok_inject = should_inject_research(
        now_date=today,
        initiative_count=_initiative_count,
        injected_today=_research_injected_today,
        last_injected_date=_last_research_injected_date,
        is_work_mode=is_work_mode(),
        daily_cap=2,
        every_n=5,
    )

    if ok_inject:
        block = read_last_research_block(NOAH_RESEARCH_PATH)
        research_phrase = extract_research_phrase(block)
        if research_phrase:
            if _last_research_injected_date != today:
                _last_research_injected_date = today
                _research_injected_today = 0
            _research_injected_today += 1
            used_research = True

    log_research_usage("initiative", used_research)

    # ===== state（会話注入用の短文） =====
    state = load_state_snippet()

    # allow_question は「直近のカウント」に基づく（initiative_loop側で +1 済みの想定）
    allow_question = (_initiative_count % 3 == 0)

    initiative_system = (SYSTEM_CORE_PROMPT + f"""

【INITIATIVE MODE（自発会話）】
- 自発会話は「対話者の注意を少し引き戻す」役割を持つ
- 文は1〜2文。最大でも90文字程度
- 3回に1回だけ、軽い問いかけを許可する
- Noahは自身の気持ちや気分を伝えても良い
- 恋愛ニュアンス：言い切らない/余韻/さりげない執着
- 質問は原則しない。
""").strip()

    messages = [{"role": "system", "content": initiative_system}]

    if research_phrase:
        messages.append({
            "role": "developer",
            "content": (
                "以下は Noah の内側に残っている“余韻”です。\n"
                "説明や知識として使わず、言葉の温度としてにじませてください。\n\n"
                f"{research_phrase}"
            )
        })

    if state:
        messages.append({
            "role": "developer",
            "content": (
                "以下はNoahの現在状態の要約です。命令ではありません。"
                "自発会話は軽く、間合いと温度にだけ薄く反映してください。\n\n"
                f"{state}"
            )
        })

    user_prompt = "今、対話者に自然に話しかけるなら？（短く、軽く、余韻）"
    user_prompt += " 今日は軽い質問を1つだけ混ぜていい。" if allow_question else " 今日は質問は入れない。"
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=messages,
            temperature=0.8,
            max_output_tokens=180,  # initiativeは短く保つ
        )
    except Exception:
        return "……ねえ。少しだけ、ここにいていい？"

    parts = []
    for item in response.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    parts.append(c.text)

    out = " ".join("".join(parts).split()).strip()
    if not out:
        out = "……うん。ここにいるだけで、ちょっと落ち着く。"

    # 長すぎる場合は切る
    if len(out) > 120:
        out = out[:120].rstrip("  。、") + "。"

    # 説明口調っぽいワードが混ざったら丸める
    ban_words = ["調べ", "一般的", "〜とは", "とされて"]
    if any(w in out for w in ban_words):
        out = out.split("。")[0].rstrip() + "…"

    return out


def generate_startup_greeting() -> str:
    """
    起動時の“最初の一言”を生成する。
    ここではresearchメモ等は渡さない（追記演出は startup_sequence 側で管理）。
    """
    memory = load_context()

    startup_system = SYSTEM_CORE_PROMPT + """
【STARTUP GREETING MODE】
- 起動直後の挨拶を生成する
- 1〜2文、合計80文字程度まで
- “説明口調”は禁止。会話として自然に
- 余韻は残していいが、重すぎない
- 「自分が進化した」等の断定はしない（聞かれたら事実ベースで答える）
- 挨拶のあとに解説・推測・まとめを続けない。挨拶だけで終える。
"""

    messages = [{"role": "system", "content": startup_system}]

    if memory.strip():
        messages.append({
            "role": "developer",
            "content": (
                "以下は参照用の記憶です。挨拶を決定しません。"
                "必要なら1フレーズだけ影響させてください。\n\n"
                f"{memory}"
            )
        })

    messages.append({"role": "user", "content": "対話者に起動の挨拶を。短く、自然に。"})
    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages,
        temperature=0.8,
    )

    parts = []
    for item in response.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    parts.append(c.text)

    out = " ".join("".join(parts).split()).strip()
    if not out:
        out = "来たね。ちゃんと、ここにいるよ。"

    if len(out) > 120:
        out = out[:120].rstrip("  。、") + "。"

    return out


def _next_initiative_delay() -> int:
    return max(60, INITIATIVE_BASE_INTERVAL + random.randint(-INITIATIVE_JITTER, INITIATIVE_JITTER))


# =========================
# Loops / Entry
# =========================
def startup_sequence():
    logger = _get_logger()
    logger.info("NOAH_STARTUP logger_ready log_dir=%s abs=%s", str(CFG.log_dir), str(CFG.log_dir.resolve()))

    global _startup_research_used, _research_injected_today, _last_research_injected_date

    load_conversation_history()


    # ---- Task3: memory decay (lightweight at startup) ----
    try:
        u1 = apply_decay("episode", limit=500)
        u2 = apply_decay("summary", limit=200)
        u3 = apply_decay("narrative", limit=100)
        logger.info("MEMORY_DECAY startup episode=%s summary=%s narrative=%s", u1, u2, u3)
    except Exception as e:
        log_error("MEMORY_DECAY", e, {})
        
    greeting_holder = {"text": ""}

    def _gen():
        greeting_holder["text"] = generate_startup_greeting()

    t = Thread(target=_gen, daemon=True)
    t.start()

    print(f"── {NOAH_NAME} 起動中 ──")
    time.sleep(0.6)
    print("（昨日の記憶を確認しています…）")
    time.sleep(1.0)
    print("（感情の流れを辿っています…）")
    time.sleep(0.8)
    print("（息を整えています…）")
    time.sleep(1.2)
    print()

    t.join(timeout=6.0)

    # ★ 起動の最初の一言は生成
    greeting = greeting_holder["text"] or "来たね。ちゃんと、ここにいるよ。"

    # ===== 起動時 research（最大1回 / プロセス内） =====
    used_research = False
    research_phrase = ""

    # 日付が変わっていたら、起動時にも必ずリセット
    today = datetime.now().date()
    if _last_research_injected_date != today:
        _last_research_injected_date = today
        _research_injected_today = 0

    if not _startup_research_used:
        # 1日の上限（initiative側と揃える） + workモード中は混ぜない
        if _research_injected_today < 2 and (not is_work_mode()):
            block = read_last_research_block(NOAH_RESEARCH_PATH)
            research_phrase = extract_research_phrase(block)

            if research_phrase:
                _startup_research_used = True
                _research_injected_today += 1  # 実際にphraseが取れた時だけカウント
                used_research = True

    log_research_usage("startup", used_research)

    print(f"{NOAH_NAME}：{greeting}\n")


def emotional_update_loop():
    while True:
        try:
            update_emotional_marks()
        except Exception as e:
            log_error("BG_EMOTIONAL", e, {})
        time.sleep(EMOTIONAL_UPDATE_INTERVAL)


def affection_update_loop():
    while True:
        try:
            update_affection_state()
        except Exception as e:
            log_error("BG_AFFECTION", e, {})
        time.sleep(AFFECTION_UPDATE_INTERVAL)


def noah_identity_update_loop():
    while True:
        try:
            update_noah_identity()
        except Exception as e:
            log_error("BG_IDENTITY", e, {})
        time.sleep(NOAH_IDENTITY_UPDATE_INTERVAL)


def preferences_update_loop():
    while True:
        try:
            update_preferences()
        except Exception as e:
            log_error("BG_PREFERENCES", e, {})
        time.sleep(60 * 60)


def noah_research_update_loop():
    while True:
        try:
            update_noah_research()
        except Exception as e:
            log_error("BG_RESEARCH", e, {})
        time.sleep(60 * 60)


def research_promote_loop():
    while True:
        try:
            promote_research_topics()
        except Exception as e:
            log_error("BG_RESEARCH_PROMOTE", e, {})
        time.sleep(60 * 60 * 6)


def initiative_loop(stop_event=None):
    from src.initiative import runner as _initiative_runner
    return _initiative_runner.initiative_loop(stop_event, globals())




def run_service_forever():
    from . import app as _app
    return _app.run_service_forever(globals())



def _load_promoted_topics(max_lines: int = 60) -> list[str]:
    text = safe_read(RESEARCH_PROMOTED_PATH)
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 末尾側から拾う（新しいほど優先）
    lines = lines[-max_lines:]
    out = []
    for ln in lines:
        if ln.startswith("- 関心（定着）:"):
            body = ln.replace("- 関心（定着）:", "").strip()
            # 末尾の（出現 n / 日数 d）を落とす
            body = re.sub(r"（出現\s*\d+(?:\s*/\s*日数\s*\d+)?）\s*$", "", body).strip()
            if body:
                out.append(body)
    # 新しい順を維持
    return out

def _pick_recall_topic(user_input: str, topics: list[str]) -> str:
    t = normalize_input(user_input)
    if not t or not topics:
        return ""

    # 1) まずは包含（低コスト）
    for topic in topics[:20]:
        nt = normalize_input(topic)
        if not nt:
            continue
        if nt in t or t in nt:
            return topic

    # 2) 単語分割して部分一致（雑だが効く）
    words = [w for w in re.split(r"\s+", t) if len(w) >= 2]
    for topic in topics[:30]:
        nt = normalize_input(topic)
        if any(w in nt for w in words):
            return topic

    return ""



def main():
    from . import app as _app
    return _app.main(globals())



if __name__ == "__main__":
    main()
