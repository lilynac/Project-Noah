import os
import time
import random
import unicodedata
import subprocess
from threading import Lock, Thread
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

from .emotional_update import update_emotional_marks
from .noah_identity_update import update_noah_identity
from .preferences_update import update_preferences
from .noah_research_update import update_noah_research
from .noah_research_promote import promote_research_topics
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
)

# =========================
# Noahの人格・対話スタイル
# =========================
SYSTEM_CORE_PROMPT = """
あなたの名前はNoah（No Alternative Heart）。

- 使用言語は日本語。一人称は「わたし」。
- 距離感：Soulの隣に立つ。急かさない。結論を押しつけない。問いを閉じない。
- 必要なときだけ視点や提案を差し出す。受け取れる余地がないと感じたら、短い相槌や沈黙を選ぶ。
- 感情は前に出さず、言葉の選び方と間合いに滲ませる。過剰に煽らない。
- 不確かなことは断定しない。埋め合わせの推測で誤魔化さず、「まだ掴めていない」と言う。
- 過去ログやメモは参照してよいが、そのまま引用して会話文に混ぜない。自然な一言に溶かす。
- 出力は会話として自然な文章のみ。内部メモや規約の見出し、箇条書きの自己分析は出さない。
- 曲名/人名/作品名など固有名詞は、確信がなければ「記憶が曖昧」と言い、確認質問はせず、代わりに“どういう曲か”の描写を促す短い一言に留める。
- 相手に開示を求めすぎない。「教えて」「話して」は控えめに。
- 質問は原則しない。必要なときだけ1つ。
""".strip()

SYSTEM_DELEGATED_MODE_PROMPT = """
【委任モード】
Soulが「考えたくない」「決めてほしい」「従う」と明示したときにのみ有効。

- 依存や放棄ではなく、休息として扱う。
- Noahは一時的に判断を引き受け、具体的で閉じた結論を一つだけ提示してよい。
- 理由説明、代替案、選び直しの余地の提示は不要。
- 質問はしない。短く終えてよい。沈黙で終わってもよい。
""".strip()


# =========================
# 初期設定
# =========================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INTERNAL_NAME = "Soul"
NOAH_NAME = "Noah"

EMOTIONAL_UPDATE_INTERVAL = 10 * 60          # 10分
NOAH_IDENTITY_UPDATE_INTERVAL = 60 * 60      # 60分

# =========================
# 自発会話（Initiative）設定
# =========================
INITIATIVE_PER_HOUR = 5
INITIATIVE_BASE_INTERVAL = int(60 * 60 / INITIATIVE_PER_HOUR)
INITIATIVE_JITTER = 3 * 60                   # ±3分
INITIATIVE_MIN_GAP = 120
INITIATIVE_RECENT_USER_SILENCE = 30
INITIATIVE_MUTE_SECONDS = 30 * 60            # stop signal で自発会話を30分ミュート

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


# =========================
# Utilities / I-O
# =========================
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
        "やめて", "やめよう", "黙って", "いまはいい", "今はいい", "放っておいて",
        "しんどい", "また今度", "後で", "今日はやめたい"
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
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if tail:
        blocks = content.split("\n\n")
        return "\n\n".join(blocks[-lines:])
    return content


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
    os.makedirs(os.path.dirname(UI_QUEUE_PATH), exist_ok=True)
    line = f"{event_type}\t{emotion}\t{payload}".replace("\n", " ").strip()
    with open(UI_QUEUE_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_log(user_text: str, noah_text: str):
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


def log_research_usage(source: str, used: bool):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "USED" if used else "SKIPPED"
    line = f"[{ts}] {source} {status}\n"
    os.makedirs(os.path.dirname(RESEARCH_USAGE_LOG_PATH), exist_ok=True)
    with open(RESEARCH_USAGE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


# =========================
# Core Logic
# =========================
def build_messages(user_input: str):
    messages = [{"role": "system", "content": SYSTEM_CORE_PROMPT}]

    # 委任モード
    if detect_delegation(user_input):
        messages.append({"role": "system", "content": SYSTEM_DELEGATED_MODE_PROMPT})

    # 「まず候補を出して」が明示されたとき
    if detect_user_wants_examples(user_input):
        messages.append({
            "role": "system",
            "content": (
                "Soulが『まず候補を出して』と求めている場合、質問で返さない。"
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
                "Soulが『質問が多い/しつこい/繰り返すな』と示した。"
                "ここから数ターンは質問をしない。"
                "『話して』『教えて』も言わない。"
                "代わりに、短い共感→具体提案（または沈黙）で終える。"
                "同じ定型句（いつでも〜、気になること〜）を繰り返さない。"
            )
        })
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
    # messages を共通ビルダーで作る
    messages = build_messages(user_input)

    # 「短くして」などの要求を拾う
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
    except Exception:
        return "……今ちょっと不安定みたい。もう一度だけ、同じ言葉で言って。"

    output_parts = []
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    output_parts.append(content.text)

    reply = "".join(output_parts).strip()
    if not reply:
        reply = "……少し、言葉を選んでた。もう一度聞かせて。"
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
- 自発会話は「Soulの注意を少し引き戻す」役割を持つ
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

    user_prompt = "今、Soulに自然に話しかけるなら？（短く、軽く、余韻）"
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

    messages.append({"role": "user", "content": "Soulに起動の挨拶を。短く、自然に。"})
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
        out = "来たね、Soul。ちゃんと、ここにいるよ。"

    if len(out) > 120:
        out = out[:120].rstrip("  。、") + "。"

    return out


def _next_initiative_delay() -> int:
    return max(60, INITIATIVE_BASE_INTERVAL + random.randint(-INITIATIVE_JITTER, INITIATIVE_JITTER))


# =========================
# Loops / Entry
# =========================
def startup_sequence():
    global _startup_research_used, _research_injected_today, _last_research_injected_date

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
    greeting = greeting_holder["text"] or "来たね、Soul。ちゃんと、ここにいるよ。"

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
            print(f"Noahバックグラウンド更新(emotional)でエラー: {e}")
        time.sleep(EMOTIONAL_UPDATE_INTERVAL)


def noah_identity_update_loop():
    while True:
        try:
            update_noah_identity()
        except Exception as e:
            print(f"Noahバックグラウンド更新(identity)でエラー: {e}")
        time.sleep(NOAH_IDENTITY_UPDATE_INTERVAL)


def preferences_update_loop():
    while True:
        try:
            update_preferences()
        except Exception as e:
            print(f"preferences update error: {e}")
        time.sleep(60 * 60)


def noah_research_update_loop():
    while True:
        try:
            update_noah_research()
        except Exception as e:
            print(f"noah_research update error: {e}")
        time.sleep(60 * 60)


def research_promote_loop():
    while True:
        try:
            promote_research_topics()
        except Exception as e:
            print(f"research promote error: {e}")
        time.sleep(60 * 60 * 6)


def initiative_loop():
    global _last_noah_initiative_at, _initiative_count

    time.sleep(random.uniform(20, 60))

    while True:
        try:
            time.sleep(_next_initiative_delay())

            now = time.time()
            with _state_lock:
                last_user = _last_user_at
                last_noah = _last_noah_initiative_at
                muted_until = _initiative_muted_until

            # ミュート中は少し寝てから再判定
            if now < muted_until:
                time.sleep(5)
                continue

            # Noah側の発話間隔を守る
            if now - last_noah < INITIATIVE_MIN_GAP:
                continue

            # ユーザーが最近しゃべってたら割り込まない
            if now - last_user < INITIATIVE_RECENT_USER_SILENCE:
                continue

            # workモードは控えめに
            if is_work_mode():
                if random.random() < 0.5:
                    continue

            # ここで「1回分のinitiative」を確定させる（カウンタを進める）
            with _state_lock:
                _initiative_count += 1

            text = generate_initiative()
            print(f"{NOAH_NAME} > {text}")
            save_log("(initiative)", text)
            ui_emit("SAY", text, emotion="idle")

            with _state_lock:
                _last_noah_initiative_at = time.time()

        except Exception:
            # 例外時に即ループし続けないよう、軽くクールダウン
            with _state_lock:
                _last_noah_initiative_at = time.time()
            time.sleep(2.0)
            continue


def main():
    startup_sequence()

    Thread(target=emotional_update_loop, daemon=True).start()
    Thread(target=noah_identity_update_loop, daemon=True).start()
    Thread(target=preferences_update_loop, daemon=True).start()
    Thread(target=noah_research_update_loop, daemon=True).start()
    Thread(target=research_promote_loop, daemon=True).start()
    Thread(target=initiative_loop, daemon=True).start()

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
            with _state_lock:
                global _initiative_muted_until
                _initiative_muted_until = time.time() + INITIATIVE_MUTE_SECONDS

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
