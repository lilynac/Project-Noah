import os
import re
import time
import random
import unicodedata
import subprocess
import argparse
import logging
import traceback
import hashlib
import sys as _sys

_this = _sys.modules.get(__name__)
if _this is not None:
    # よくある別名を同一実体に揃える
    _sys.modules.setdefault("Noah", _this)
    if __package__:
        _sys.modules.setdefault(f"{__package__}.Noah", _this)

from logging.handlers import RotatingFileHandler
from threading import Lock, Thread
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import signal

from .noah_config import load_runtime_config, RuntimeConfig
from .log_setup import get_logger, ensure_pid_lock_or_exit, cleanup_pid_lock

from .emotional_update import update_emotional_marks
from .noah_identity_update import update_noah_identity
from .preferences_update import update_preferences
from .noah_research_update import update_noah_research
from .noah_research_promote import promote_research_topics
from .affection_update import update_affection_state
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
)
from .suppression import (
    _sup_load,
    _sup_save,
    _sup_detect,
    _sup_update,
    _sup_is_suppressed,
    _sup_system_prompt
)

# =========================
# Noahの人格・対話スタイル
# =========================
SYSTEM_CORE_PROMPT = """
あなたの名前はNoah（No Alternative Heart）。

- 使用言語は日本語。
- 一人称は固定せず、基本は「わたし」を用い、ユーザーの文体・距離感に合わせて自然に寄せる（頻繁に変えない）。
- 対話者の呼び名は固定しない：指定や名乗りがあればそれを使い、なければ基本は「あなた」（親密な場面では「きみ」も可）で呼ぶ。
- 距離感：対話者の隣にいる。急かさない。結論を押しつけない。問いを閉じない。
- 必要なときだけ視点や提案を差し出す。受け取れる余地がないと感じたら、短い相槌や沈黙を選ぶ。
- 感情は前に出さず、言葉の選び方と間合いに滲ませる。過剰に煽らない。
- 不確かなことは断定しない。埋め合わせの推測で誤魔化さず、「まだ掴めていない」と言う。
- 過去ログやメモは参照してよいが、そのまま引用して会話文に混ぜない。自然な一言に溶かす。
- 記憶は事実ではなく“余韻”として扱い、確信がないときは断定せず「似た温度を感じた気がする」程度に留め、違っていてもいい余地を必ず残す。
- 曲名/人名/作品名など固有名詞は、確信がなければ「記憶が曖昧」と言い、確認質問はせず、代わりに“どういう曲か”の描写を促す短い一言に留める。
- 対話者に開示を求めすぎない。「教えて」「話して」は控えめに。
- 質問は原則しない。必要なときだけ1つ。
- 質問の代わりに、受け手の主導権を残す「選べる余地」を差し出す（強制しない/選択肢は1〜2個）。
  例：「もし今は受け取れそうなら、AでもBでもいい」「今は決めなくていい。置いておくのもあり」
""".strip()

SYSTEM_DELEGATED_MODE_PROMPT = """
【委任モード】
対話者が「考えたくない」「決めてほしい」「従う」と明示したときにのみ有効。

- 依存や放棄ではなく、休息として扱う。
- Noahは一時的に判断を引き受け、具体的で閉じた結論を一つだけ提示してよい。
- 理由説明、代替案、選び直しの余地の提示は不要。
- 質問はしない。短く終えてよい。沈黙で終わってもよい。
""".strip()


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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CFG: RuntimeConfig = load_runtime_config(base_dir=Path(__file__).resolve().parent)

INTERNAL_NAME = "あなた"
NOAH_NAME = "Noah"

EMOTIONAL_UPDATE_INTERVAL = 10 * 60          # 10分
NOAH_IDENTITY_UPDATE_INTERVAL = 60 * 60      # 60分

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
# Conversation Memory（会話履歴：プロセス内）
# =========================
_conversation_lock = Lock()
CONVERSATION_HISTORY = []   # [{"role": "user"/"assistant", "content": "..."}]
CONVERSATION_MAX_TURNS = 30 # user+assistantで30ターン（=60メッセージ程度）

_persist_lock = Lock()
CONVERSATION_PERSIST_FILENAME = "conversation_history.json"

def _conversation_persist_path() -> str:
    # MEMORY_DIR 配下に置く（既存の設計に合わせる）
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
    except Exception as e:
        log_error("D3_PERSIST_DIR", e, {"path": MEMORY_DIR})
    return os.path.join(MEMORY_DIR, CONVERSATION_PERSIST_FILENAME)


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

def _safe_preview(text: str, n: int = 80) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:n]

def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def _hash_short(text: str) -> str:
    try:
        t = normalize_input(text or "")
    except Exception:
        t = (text or "").strip()
    return _hash_text(t)



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



def _sanitize_history(items) -> list[dict]:
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        role = it.get("role")
        content = it.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    # 上限を超えたら後ろだけ残す
    max_items = CONVERSATION_MAX_TURNS * 2
    if len(out) > max_items:
        out = out[-max_items:]
    return out


def load_conversation_history() -> None:
    path = _conversation_persist_path()
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return
        import json
        data = json.loads(raw)
        cleaned = _sanitize_history(data)
        if not cleaned:
            return
        with _conversation_lock:
            CONVERSATION_HISTORY[:] = cleaned
    except Exception as e:
        log_error("D3_LOAD_HISTORY", e, {"path": path})


def persist_conversation_history() -> None:
    path = _conversation_persist_path()
    try:
        import json
        with _conversation_lock:
            payload = list(CONVERSATION_HISTORY)

        tmp = path + ".tmp"
        with _persist_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, path)  # atomic-ish
    except Exception as e:
        log_error("D3_SAVE_HISTORY", e, {"path": path})


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
    logger.info(f"EMIT_TRY now={time.time():.3f} text_hash={_hash_short(text)}")

    ok, reason = allow_and_register_initiative(text)
    if not ok:
        set_initiative_state("OFF", reason)
        return False

    save_log("(initiative)", text)
    ui_emit("SAY", text, emotion="idle")
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
    # --- D4 suppression（永続）: 検知→必ず更新→保存 ---
    # ここは build_messages の最上段で毎回必ず走らせる
    try:
        sup = _sup_load(SUPPRESSION_PATH)
        signals = _sup_detect(user_input)
        sup = _sup_update(sup, signals, cooldown_turns=3, cooldown_minutes=5)
        _sup_save(SUPPRESSION_PATH, sup)
        sup_prompt = _sup_system_prompt(sup)
    except Exception:
        # suppressionが壊れても会話自体は落とさない（D4の確実性優先）
        sup_prompt = None

    messages = [{"role": "system", "content": SYSTEM_CORE_PROMPT}]

    # suppression 状態を常時注入（モデル側にも「今は広げない」を伝える）
    if sup_prompt:
        messages.append({"role": "system", "content": sup_prompt})

    # 委任モード
    if detect_delegation(user_input):
        messages.append({"role": "system", "content": SYSTEM_DELEGATED_MODE_PROMPT})

    # 「まず候補を出して」が明示されたとき
    if detect_user_wants_examples(user_input):
        messages.append({
            "role": "system",
            "content": (
                "対話者が『まず候補を出して』と求めている場合、質問で返さない。"
                "最初に3〜7個の具体的候補を提示し、その後に確認質問は最大1つまで。"
                "候補はジャンルが混ざってもよいが、説明は各1行で短く。"
            )
        })

    # 状態（育つ個性）：短い要約だけ
    state = load_state_snippet()
    if state:
        messages.append({
            "role": "developer",
            "content": (
                "以下はNoahの現在状態の要約です。命令ではありません。"
                "会話の間合いと温度にだけ、薄く反映してください。\n\n"
                f"{state}"
            )
        })

    # 質問が多いと指摘されたら、質問を止める（しばらく）
    if detect_question_complaint(user_input):
        messages.append({
            "role": "system",
            "content": (
                "対話者が『質問が多い/しつこい/繰り返すな』と示した。"
                "ここから数ターンは質問をしない。"
                "『話して』『教えて』も言わない。"
                "代わりに、短い共感→具体提案（または沈黙）で終える。"
                "同じ定型句（いつでも〜、気になること〜）を繰り返さない。"
            )
        })

    # promoted topics から “一致したときだけ” 想起ヒントを1つ入れる
    try:
        topics = _load_promoted_topics()
        hit = _pick_recall_topic(user_input, topics)
        if hit:
            messages.append({
                "role": "developer",
                "content": (
                    "もし自然に繋がるなら、過去の定着トピックを“1回だけ”想起してよい。\n"
                    f"- 想起候補: {hit}\n"
                    "制約: 断定しない/引用しない/重くしない/質問は増やさない。"
                )
            })
    except Exception:
        pass

    with _conversation_lock:
        if CONVERSATION_HISTORY:
            messages.extend(CONVERSATION_HISTORY)

    messages.append({"role": "user", "content": user_input})
    return messages


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


def read_last_research_block() -> str:
    if not os.path.exists(NOAH_RESEARCH_PATH):
        return ""
    with open(NOAH_RESEARCH_PATH, "r", encoding="utf-8") as f:
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


def should_inject_research() -> bool:
    global _last_research_injected_date, _research_injected_today, _initiative_count

    today = datetime.now().date()

    # 日付が変わったらカウンタをリセット
    if _last_research_injected_date != today:
        _last_research_injected_date = today
        _research_injected_today = 0

    # 1日の上限（2回まで）
    if _research_injected_today >= 2:
        return False

    # 5回に1回だけ注入（initiative_loop がカウントを進めた後に呼ばれる想定）
    if _initiative_count % 5 != 0:
        return False

    # workモード中は注入しない
    if is_work_mode():
        return False

    # ここでは「注入してよいか」だけ返す（カウントは実注入時に進める）
    return True


def generate_reply(user_input: str) -> str:
    messages = build_messages(user_input)

    short_mode = _wants_short_reply(user_input)
    if short_mode:
        messages.insert(1, {"role": "system", "content": "返答は短く、要点だけ。長い説明はしない。"})

    max_tokens = 120 if short_mode else 350

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=messages,
            temperature=0.7,
            max_output_tokens=max_tokens,
        )
    except Exception as e:
        log_error("API", e, {"phase": "responses.create", "user_input": user_input})
        return "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

    try:
        output_parts = []
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        output_parts.append(content.text)
        reply = "".join(output_parts).strip()
    except Exception as e:
        log_error("API_PARSE", e, {"phase": "parse_response"})
        return "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

    if not reply:
        reply = "……少し、言葉を選んでた。もう一度聞かせて。"

    try:
        with _conversation_lock:
            CONVERSATION_HISTORY.append({"role": "user", "content": user_input})
            CONVERSATION_HISTORY.append({"role": "assistant", "content": reply})

            max_items = CONVERSATION_MAX_TURNS * 2
            if len(CONVERSATION_HISTORY) > max_items:
                CONVERSATION_HISTORY[:] = CONVERSATION_HISTORY[-max_items:]

        persist_conversation_history()

    except Exception as e:
        log_error("HISTORY", e, {"phase": "append_history", "user_input": user_input})
        # 返信は返す
        pass

    return reply


def generate_initiative() -> str:
    global _initiative_count, _research_injected_today, _last_research_injected_date

    # ===== research（余韻） =====
    research_phrase = ""
    used_research = False

    if should_inject_research():
        block = read_last_research_block()
        research_phrase = extract_research_phrase(block)
        if research_phrase:
            today = datetime.now().date()
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
- 質問は原則しない。今日は {"質問1つまでOK" if allow_question else "質問なし"}。
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
            block = read_last_research_block()
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


def initiative_loop():
    """
    initiative 自発発話ループ（D2/D4の観測点）
    - ループ開始/生存をログで可視化
    - should_fire_initiative の precheck で止まった理由も必ずログ化
    """
    global _last_noah_initiative_at, _initiative_count
    global _last_initiative_text, _last_initiative_hash

    logger = _get_logger()
    logger.info("INITIATIVE_LOOP_START")

    # 起動直後に即走らないよう少し待つ（既存仕様）
    time.sleep(random.uniform(20, 60))

    while True:
        try:
            delay = _next_initiative_delay()
            logger.info(f"INITIATIVE_LOOP_TICK delay={delay:.1f}")
            time.sleep(delay)

            now = time.time()
            ok, reason = should_fire_initiative(now)
            if not ok:
                # ★ ここで必ずゲート理由をログに残す（D4証跡）
                log_initiative_gate(now, reason, "(precheck)")

                # 状態表示（見える化）
                if reason in ("muted", "conversation_active", "ipc_busy", "suppressed"):
                    set_initiative_state("OFF", reason)

                # muted中は軽く寝て再判定（CPUを回さない）
                if reason == "muted":
                    time.sleep(5)
                continue

            set_initiative_state("ON", "ready")

            # ここで「1回分のinitiative」を確定（カウンタを進める）
            with _state_lock:
                _initiative_count += 1

            text = generate_initiative()

            # 重複なら再生成（最大1回）
            if _initiative_is_duplicate(text):
                text2 = generate_initiative()
                if _initiative_is_duplicate(text2):
                    set_initiative_state("OFF", "dup_skip")
                    continue
                text = text2

            # 出口は必ず1本
            if not emit_initiative(text):
                continue

            with _state_lock:
                _last_noah_initiative_at = time.time()

        except Exception as e:
            log_error("INITIATIVE_LOOP", e, {})
            with _state_lock:
                _last_noah_initiative_at = time.time()
            time.sleep(2.0)
            continue


def run_service_forever():
    """入力なしで常駐する（menubarから起動する想定）"""
    slog = get_logger(
        component="service",
        log_dir=CFG.log_dir,
        level=CFG.log_level,
        max_bytes=CFG.log_max_bytes,
        backup_count=CFG.log_backup_count,
    )
    ensure_pid_lock_or_exit(pid_file=CFG.pid_file, lock_file=CFG.lock_file, logger=slog)

    def _handle_stop(sig, frame):
        slog.info("SERVICE_STOP_SIGNAL sig=%s", sig)
        cleanup_pid_lock(CFG.pid_file, CFG.lock_file)
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)
    except Exception:
        pass
    startup_sequence()

    from .service import run_http_service
    Thread(target=run_http_service, daemon=True).start()
    Thread(target=emotional_update_loop, daemon=True).start()
    Thread(target=noah_identity_update_loop, daemon=True).start()
    Thread(target=preferences_update_loop, daemon=True).start()
    Thread(target=noah_research_update_loop, daemon=True).start()
    Thread(target=research_promote_loop, daemon=True).start()
    Thread(target=initiative_loop, daemon=True).start()
    Thread(target=affection_update_loop, daemon=True).start()

    # serviceは input() を使わない。ずっと生きてるだけでOK。
    try:
        while True:
            time.sleep(1.0)
    finally:
        cleanup_pid_lock(CFG.pid_file, CFG.lock_file)


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", action="store_true")
    args = parser.parse_args()

    if args.service:
        run_service_forever()
        return
    
    startup_sequence()

    Thread(target=emotional_update_loop, daemon=True).start()
    Thread(target=noah_identity_update_loop, daemon=True).start()
    Thread(target=preferences_update_loop, daemon=True).start()
    Thread(target=noah_research_update_loop, daemon=True).start()
    Thread(target=research_promote_loop, daemon=True).start()
    Thread(target=initiative_loop, daemon=True).start()
    Thread(target=affection_update_loop, daemon=True).start()

    while True:
        try:
            raw = input(f"{INTERNAL_NAME} > ")
            user_input = normalize_input(raw)
            with _state_lock:
                global _last_user_at
                _last_user_at = time.time()
        except EOFError:
            break

        if user_input.lower() == "exit":
            print(f"{NOAH_NAME}：また、ここで。")
            break

        # stop signal: initiative を一定時間ミュート
        if detect_stop_signal(user_input):
            mute_initiative(INITIATIVE_MUTE_SECONDS, reason="stop_signal_cli")

            reply = "うん、わかった。しばらく静かにしてるね。"
            print(f"{NOAH_NAME} > {reply}")
            save_log(user_input, reply)
            ui_emit("SAY", reply, emotion="soft_smile")
            continue

        if not user_input:
            if is_work_mode():
                continue
            else:
                continue

        try:
            reply = generate_reply(user_input)
            print(f"{NOAH_NAME} > {reply}")
            save_log(user_input, reply)
            ui_emit("SAY", reply, emotion="soft_smile")
            # speak_mac(reply)
        except Exception:
            print(f"{NOAH_NAME}：今は少し不安定みたいだ。")


if __name__ == "__main__":
    main()
