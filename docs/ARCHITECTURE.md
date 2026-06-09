# ARCHITECTURE.md

Project Noah の内部設計メモです。

README は初見の入口に留め、この資料では構成・責務・データの流れ・主要モジュールを説明します。

---

## 全体像

Noah は、ローカルで常駐する PyQt6 アプリケーションです。

大きく分けると以下の層で構成されています。

```text
User
  ↓
PyQt6 Tray / Overlay
  ↓
localhost HTTP IPC
  ↓
Noah runtime
  ↓
Message builder / Memory / Initiative / LLM
  ↓
OpenAI API + SQLite + local files
```

GUI と応答生成処理は直接密結合させず、localhost HTTP IPC と `data/memory/ui_queue.txt` を使って緩くつないでいます。

---

## 起動の流れ

標準起動は以下です。

```bash
python -m src
```

`src/__main__.py` が起動入口です。

主な流れ:

1. `bootstrap_once()` が `data/` と `db/` を初期化
2. `src.Noah` を import
3. 通常起動では `qt_entry.main()` を実行
4. Qt / Tray / Overlay を起動
5. HTTP IPC を `127.0.0.1:8765` で起動
6. 自発発話や感情更新などのバックグラウンドループを起動

---

## 主要ディレクトリ

```text
src/
├── __main__.py
├── Noah.py
├── app.py
├── qt_entry.py
├── tray.py
├── desktop_noah.py
├── service.py
├── bootstrap.py
├── db.py
├── noah_config.py
├── noah_prompts.py
├── message_builder.py
├── conversation_history.py
├── llm_trace.py
├── memory/
├── initiative/
├── dialogue/
└── legacy/
```

---

## 主要モジュールと責務

### `src/__main__.py`

`python -m src` の起動入口です。

- `--service`
- `--once`
- 通常 Qt 起動

を振り分けます。

### `src/Noah.py`

Noah 本体の互換用中心モジュールです。

以前は人格プロンプト、会話履歴、LLM trace、message build、initiative loop、CLI 入口を多く抱えていました。現在は一部を以下の専用モジュールへ分離しています。

- `noah_prompts.py`
- `llm_trace.py`
- `conversation_history.py`
- `message_builder.py`
- `initiative/runner.py`
- `app.py`

既存コードから参照されている関数名との互換性を保つため、`Noah.py` は完全な薄い入口ではなく、まだ集約モジュールとして残しています。

### `src/app.py`

CLI / service 常駐系の実行処理を分けたモジュールです。

- service 常駐
- CLI 入力ループ
- stop signal の扱い
- バックグラウンド loop の起動

を扱います。

### `src/noah_prompts.py`

Noah の中核プロンプトを管理します。

- `SYSTEM_CORE_PROMPT`
- `SYSTEM_DELEGATED_MODE_PROMPT`

人格・返答方針の中心はここに置きます。

### `src/message_builder.py`

LLM に渡す messages を構築します。

主に以下を統合します。

- system prompt
- mode
- memory context
- conversation history
- suppression context
- user input
- DB から取り出した記憶

### `src/conversation_history.py`

会話履歴の保存・復元・整形を扱います。

- `data/memory/conversation_history.json`
- recent turn の抽出
- 保存前の sanitize
- 履歴上限管理

### `src/llm_trace.py`

LLM 入出力の trace ログを扱います。

- 入力 messages のコンパクト表示
- role count
- preview
- trace file の prune
- hash 表示

### `src/service.py`

localhost HTTP IPC を提供します。

主な endpoint:

- `GET /health`
- `POST /chat`
- `POST /talk`

`/chat` と `/talk` はどちらも会話入力として使えます。

### `src/qt_entry.py`

現在の標準 GUI 起動です。

- PyQt6 application
- System Tray
- Overlay
- service thread

をまとめて起動します。

### `src/tray.py`

System Tray メニューを扱います。

- Talk
- Mode 切り替え
- Quit

### `src/desktop_noah.py`

画面上の Overlay 表示を扱います。

`data/memory/ui_queue.txt` を監視し、Noah の発話を表示します。

### `src/bootstrap.py`

初回起動に必要なファイルとディレクトリを作成します。

- `data/memory/`
- `data/notes/`
- `data/notes/hidden/`
- `db/noah.db`
- 初期 identity / state / mode ファイル

### `src/db.py`

SQLite 接続と schema 適用を扱います。

`db/schema.sql` を使って DB を初期化します。

### `src/noah_config.py`

環境変数からランタイム設定を読み込みます。

- initiative の頻度・抑制
- log 設定
- pid / lock file

詳細は [CONFIG.md](CONFIG.md) を参照してください。

---

## Memory 層

`src/memory/` は episode / summary / narrative の記憶を扱います。

```text
src/memory/
├── store.py
├── retrieve.py
├── consolidate.py
├── decay.py
├── narrative.py
├── tags.py
└── schema.sql
```

主な考え方:

- episode: 個別の出来事や会話の断片
- summary: 複数の episode をまとめた要約
- narrative: ユーザーと Noah の関係性や長期的な文脈

SQLite DB の主なテーブル:

- `episode_memories`
- `summary_memories`
- `narrative_memories`
- `entities`
- `events`
- `narratives`

---

## Initiative 層

`src/initiative/` は自発発話を扱います。

```text
src/initiative/
├── context.py
├── decision.py
├── generation.py
├── layers.py
├── runner.py
└── signals.py
```

主な責務:

- 自発発話してよい状況か判断する
- 連投や割り込みを抑制する
- 作業モードでは控えめにする
- memory / affection / loneliness / recent user activity を見て発話候補を作る
- `ui_queue.txt` に発話を送る

`runner.py` は以前 `Noah.py` にあった `initiative_loop()` の本体です。

---

## Dialogue 層

`src/dialogue/` はテンプレート系を扱います。

```text
src/dialogue/
├── templates.py
└── templating.py
```

LLM だけに依存しすぎず、ローカルテンプレートで柔らかい返答やフォールバックを作るための層です。

---

## ローカルファイルの役割

```text
data/memory/
├── consults.txt                 # 会話ログ系
├── emotional_marks.txt          # 心理状態・対応スタンス
├── preferences.txt              # ユーザー傾向
├── preferences_history.txt      # preferences の履歴
├── noah_identity.txt            # Noah 自身の自己認識
├── noah_state.txt               # affection / trust / loneliness など
├── mode.txt                     # Normal / Work など
├── ui_queue.txt                 # Overlay 表示キュー
├── runtime_state.json           # 実行時状態
├── conversation_history.json    # 直近会話履歴
└── suppression.json             # 自発発話の抑制状態
```

```text
data/notes/
├── ideas.txt
├── todo.txt
└── hidden/
    ├── noah_research.txt
    └── research_usage_log.txt
```

---

## ログ設計

標準では `logs/` に出ます。

```text
logs/
├── noah.log
├── noah.errors.log
├── ipc.log
├── ipc.errors.log
└── service.log
```

`WARNING` 以上は `*.errors.log` にも出力されます。

ターミナルにも出したい場合:

```bash
NOAH_LOG_CONSOLE=1 python -m src
```

---

## 起動演出

起動時には Noah が目を覚ますような短い起動演出を表示します。

関連ファイル:

- `src/startup_display.py`
- `src/startup_templates.py`
- `data/memory/noah_state.txt`
- `data/memory/emotional_marks.txt`

`OPENAI_API_KEY` がある場合は、状態に応じた起動演出を API 生成できます。API が使えない場合や失敗した場合はローカルテンプレートへ戻ります。

---

## 現在のリファクタ方針

Noah.py を少しずつ薄くし、責務を専用モジュールへ分ける方針です。

完了済みの主な分離:

- `SYSTEM_CORE_PROMPT` → `noah_prompts.py`
- LLM trace 系 → `llm_trace.py`
- 会話履歴 → `conversation_history.py`
- `build_messages()` → `message_builder.py`
- `initiative_loop()` → `initiative/runner.py`
- CLI / service 入口 → `app.py`

今後の理想形:

```text
Noah.py      # 互換用ラッパー
app.py       # 実行入口
runtime.py   # 共有状態 / dependency container
```

`Noah.py` を急に消すと既存 import との互換性が壊れやすいため、段階的に薄くしていきます。
