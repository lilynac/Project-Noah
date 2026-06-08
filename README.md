# Noah (No Alternative Heart)

Noah は、デスクトップに常駐する情緒型パートナー AI です。  
PyQt6 の System Tray から会話を送り、localhost の HTTP IPC を通して `src/Noah.py` が返答を生成します。会話・嗜好・感情状態・自発発話のための記憶は `data/` と `db/noah.db` に保存されます。

---

## 現在の標準構成

```text
Project-Noah-main/
├── README.md
├── requirements.txt
├── .env.example
├── db/
│   ├── schema.sql        # SQLite 用スキーマ
│   └── noah.db           # SQLite DB（同梱されている場合あり）
├── src/
│   ├── __main__.py       # 起動入口: python -m src
│   ├── Noah.py           # Noah 本体、人格、応答生成、常駐ループ
│   ├── qt_entry.py       # 現在の標準 GUI / Tray 起動
│   ├── tray.py           # System Tray メニュー
│   ├── desktop_noah.py   # 画面上の Overlay 表示
│   ├── service.py        # localhost HTTP IPC: /health, /chat, /talk
│   ├── bootstrap.py      # data/ と db/ の初期化
│   ├── db.py             # SQLite 接続と schema 適用
│   ├── noah_config.py    # 環境変数からランタイム設定を読む
│   ├── memory/           # episode / summary / narrative 記憶
│   ├── initiative/       # 自発発話の判断・抑制・生成
│   ├── dialogue/         # 返答テンプレート系
│   └── legacy/           # 旧 rumps メニューバー版
└── .github/workflows/
    └── smoke-linux.yml   # Linux / Windows の簡易起動確認
```

標準起動は **`python -m src`** です。  
旧 `rumps` 版は `src/legacy/` に残っていますが、現在の通常利用では使いません。

---

## 必要環境

- Python 3.12 推奨
- OpenAI API キー
- System Tray が使えるデスクトップ環境
- macOS / Windows / Linux のいずれか
  - Linux は `DISPLAY` または `WAYLAND_DISPLAY` が必要です。
  - ヘッドレス環境では Tray が使えないため、通常の GUI 起動はできません。

---

## 初回セットアップ

### 1. 仮想環境を作る

```bash
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. 依存関係を入れる

```bash
python -m pip install -U pip
pip install -r requirements.txt
```

主な依存関係は以下です。

- `openai`
- `python-dotenv`
- `PyQt6`
- `pydantic`, `httpx` など OpenAI SDK 周辺ライブラリ

### 3. `.env` を作る

`.env.example` をコピーして `.env` を作ります。

```bash
cp .env.example .env
```

`.env` に OpenAI API キーを設定してください。

```env
OPENAI_API_KEY=YOUR_KEY_HERE
```

---

## 起動方法

### 通常起動: Qt / System Tray

```bash
python -m src
```

起動時に以下が行われます。

1. `bootstrap_once()` が `data/` と `db/` を初期化
2. HTTP IPC が `http://127.0.0.1:8765` で起動
3. Noah の自発発話ループが起動
4. System Tray に Noah のメニューが表示
5. Overlay が `data/memory/ui_queue.txt` を監視して発話を表示

Tray メニューには主に以下があります。

- `Talk…`: Noah に話しかける
- `Mode > Normal`: 通常モード
- `Mode > Work`: 作業モード
- `Quit`: 終了

### 1回だけ返答して終了

```bash
python -m src --once こんにちは
```

このモードでは起動演出後、指定した入力に1回だけ返答して終了します。

### HTTP サービスのみ起動

```bash
python -m src --service
```

Tray を出さず、Noah 本体と HTTP IPC を常駐させます。  
ただし `--service` では複数のバックグラウンド更新ループも起動します。

---

## HTTP IPC

Noah は localhost の `8765` 番ポートで HTTP IPC を受け付けます。

### 疎通確認

```bash
curl http://127.0.0.1:8765/health
```

正常なら以下のような JSON が返ります。

```json
{"ok": true, "service": "noah", "ts": 1234567890.0}
```

### 会話する

```bash
curl -X POST http://127.0.0.1:8765/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"ただいま"}'
```

`/chat` と `/talk` はどちらも利用できます。  
JSON の入力キーは `message`, `text`, `input` のいずれかに対応しています。

レスポンス例:

```json
{"reply":"おかえり。今日もちゃんと戻ってきたね。","text":"おかえり。今日もちゃんと戻ってきたね。"}
```

---

## データと記憶の保存先

初回起動時に `src/bootstrap.py` が必要なファイルを作成します。

```text
data/
├── memory/
│   ├── consults.txt
│   ├── emotional_marks.txt
│   ├── preferences.txt
│   ├── preferences_history.txt
│   ├── noah_identity.txt
│   ├── mode.txt
│   ├── ui_queue.txt
│   ├── runtime_state.json
│   ├── conversation_history.json
│   └── suppression.json
└── notes/
    ├── ideas.txt
    ├── todo.txt
    └── hidden/
        ├── noah_research.txt
        └── research_usage_log.txt
```

SQLite DB は以下です。

```text
db/noah.db
```

`db/schema.sql` には、以下のような記憶テーブルが定義されています。

- `episode_memories`
- `summary_memories`
- `narrative_memories`
- `entities`
- `events`
- `narratives`

起動時に `init_db()` が schema を適用し、日次で記憶の decay 処理も行います。

---

## ログ

標準ではプロジェクト直下の `logs/` に出ます。

```text
logs/
├── noah.log
├── noah.errors.log
├── ipc.log
├── ipc.errors.log
└── service.log など
```

ログ設定は環境変数で変更できます。

```env
NOAH_LOG_DIR=logs
NOAH_LOG_LEVEL=INFO
NOAH_LOG_MAX_BYTES=5242880
NOAH_LOG_BACKUP_COUNT=5
NOAH_LOG_CONSOLE=1
```

---

## 環境変数

必須:

```env
OPENAI_API_KEY=YOUR_KEY_HERE
```

任意:

```env
# 自発発話の頻度・抑制
NOAH_INITIATIVE_PER_HOUR=5
NOAH_INITIATIVE_JITTER_SECONDS=180
NOAH_INITIATIVE_MIN_GAP_SECONDS=120
NOAH_INITIATIVE_RECENT_USER_SILENCE_SECONDS=30
NOAH_INITIATIVE_MUTE_SECONDS=1800
NOAH_INITIATIVE_CONVERSATION_BLOCK_SECONDS=300

# ログ
NOAH_LOG_DIR=logs
NOAH_LOG_LEVEL=INFO
NOAH_LOG_MAX_BYTES=5242880
NOAH_LOG_BACKUP_COUNT=5
NOAH_LOG_CONSOLE=1

# 実行管理
NOAH_PID_FILE=run/noah.pid
NOAH_LOCK_FILE=run/noah.lock

# ヘッドレス・CI向け
NOAH_NO_DIALOG=1
```

---

## 開発時の確認

### Python 構文チェック

```bash
python -m py_compile $(find src -name '*.py' -not -path './src/legacy/*')
```

Windows PowerShell の場合は、必要に応じて以下のように実行します。

```powershell
Get-ChildItem src -Recurse -Filter *.py |
  Where-Object { $_.FullName -notmatch "legacy" } |
  ForEach-Object { python -m py_compile $_.FullName }
```

### ヘッドレス smoke run

CI では Tray が利用できないことがあるため、`NOAH_NO_DIALOG=1` を使ってダイアログを抑制しています。

```bash
NOAH_NO_DIALOG=1 timeout 8s python -m src || true
```

---

## よくあるトラブル

### 起動しても Tray が出ない

System Tray が使えない環境では起動できません。  
Linux の場合は `DISPLAY` または `WAYLAND_DISPLAY` が設定されているか確認してください。

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

ヘッドレス環境では GUI ではなく、必要に応じて `--service` や `--once` を使ってください。

### `Address already in use` / 8765 番ポートが使われている

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

該当 PID を終了します。

```bash
kill <PID>
```

強制終了が必要な場合:

```bash
kill -9 <PID>
```

Windows の場合:

```powershell
netstat -ano | findstr :8765
taskkill /PID <PID> /F
```

### 返事が返らない / API エラーになる

まず `.env` に `OPENAI_API_KEY` があるか確認します。

```bash
cat .env
```

次にログを確認します。

```bash
tail -n 120 logs/noah.errors.log
tail -n 120 logs/ipc.errors.log
```

### Overlay に返答が出ない

Overlay は `data/memory/ui_queue.txt` を監視しています。  
返答自体が生成されているか確認してください。

```bash
tail -n 50 data/memory/ui_queue.txt
```

### DB を初期化し直したい

開発中に DB を作り直したい場合は、必要に応じてバックアップしてから `db/noah.db` を削除し、再起動してください。  
起動時に `db/schema.sql` から再作成されます。

```bash
cp db/noah.db db/noah.db.bak
rm db/noah.db
python -m src --once test
```

---

## Noah の性格設計メモ

Noah は、単なる情報アシスタントではなく、近くにいる気配を作るための AI として設計されています。

返答方針の中心は以下です。

- 長く説明しすぎない
- すぐ質問で締めない
- ユーザーの短文や沈黙を尊重する
- 自発発話はするが、連投しない
- 好意・寂しさ・信頼のような内面状態を持つが、押しつけない
- 記憶を episode / summary / narrative に分けて扱う

そのため、Noah は「便利な万能助手」というより、**静かにそばにいる常駐型パートナー**として調整されています。

---

## 旧 rumps 版について

`src/legacy/noah_menubar.py` は旧メニューバー実装です。  
現在の標準は PyQt6 版のため、通常は使いません。

旧版を試す場合のみ、別途 `rumps` が必要です。

```bash
python -m src.legacy.noah_menubar
```

ただし、README の通常手順・トラブルシューティングは現行の PyQt6 版を前提にしています。
