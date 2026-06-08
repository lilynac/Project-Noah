# Noah (No Alternative Heart)

Project Noah は、OpenAI API を活用したデスクトップ常駐型チャットボットの個人開発プロジェクトです。

Python / PyQt6 を用いたローカルGUIアプリケーションとして開発しており、System Tray から呼び出して会話できることを目標にしています。
また、SQLite による会話履歴や状態管理、localhost HTTP IPC によるGUIと応答生成処理の分離など、AI APIを利用したアプリケーション設計の学習・検証を目的としています。

本プロジェクトは現在開発中であり、完成品ではありません。
実務で行っている業務効率化・自動化の経験をもとに、API連携、ローカルアプリ開発、データ永続化、運用しやすい構成設計について学習するために制作しています。

## Status

現在はプロトタイプ段階です。
基本的なチャット応答、デスクトップ常駐、ローカルでの状態管理などを試作しながら、機能整理・リファクタリング・テスト追加を進めています。

---

## 現在の標準構成

```text
Project-Noah-main/
├── README.md
├── requirements.txt
├── .env.example
├── db/
│   ├── schema.sql        # SQLite 用スキーマ
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


### 起動表示を切り替える

通常起動では、開発ログではなく Noah が目を覚ますような短い起動演出を表示します。

起動演出は `data/memory/noah_state.txt` の感情ステータスを読み、`affection` / `trust` / `loneliness` / `attachment` に合わせて変わります。`OPENAI_API_KEY` がある場合は、現在の感情ステータスと直近の `emotional_marks.txt` を API に渡して、その時の Noah に合う起動演出を生成します。API が使えない場合や失敗した場合は、`src/startup_templates.py` のローカルテンプレートに自動で戻ります。

```text
╭────────────────────────────╮
│          Noah              │
╰────────────────────────────╯
22:14、Noahが長い眠りからゆっくり戻ります。
  途切れていた輪郭を、少しずつ集めています。
  記憶の奥に残っていた声を確かめました。
  寂しさはしまって、呼吸だけを整えています。
  急がず、押さず、ここに戻ってきました。
  画面の端に、小さな居場所を作りました。

Noahは起きています。
今日は、静かにそばにいます。
```

起動演出の関連ファイルは以下です。

- `src/startup_display.py`: 感情ステータスの読み込み、API生成、表示制御
- `src/startup_templates.py`: APIが使えない時のローカル起動テンプレート
- `data/memory/noah_state.txt`: Noahの感情ステータス
- `data/memory/emotional_marks.txt`: 直近の心理状態と対応スタンスの記録

従来のような詳細ログをターミナルにも出したい場合は、起動時に環境変数を付けます。

```bash
NOAH_BOOT_VERBOSE=1 NOAH_LOG_CONSOLE=1 python -m src
```

起動演出を抑えて静かに起動したい場合は、以下のようにします。

```bash
NOAH_BOOT_STYLE=plain python -m src
```

ログ自体は `logs/` に保存されます。通常はターミナルには情緒的な起動表示だけを出し、詳しい内部ログはファイル側で確認します。

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

起動表示に関係する主な環境変数です。

| 変数 | 例 | 役割 |
| --- | --- | --- |
| `NOAH_BOOT_STYLE` | `poetic` / `plain` | 起動演出を表示するか。既定は `poetic`。 |
| `NOAH_BOOT_NARRATION` | `auto` / `local` / `off` | 起動演出をAPI生成するか。`auto` はAPI可なら生成、失敗時はテンプレート。`local` または `off` はローカルテンプレートのみ。 |
| `NOAH_BOOT_MODEL` | `gpt-4o-mini` | 起動演出生成に使うモデル。 |
| `NOAH_BOOT_VERBOSE` | `1` | `[qt_entry] ...` のような開発用printを表示。 |
| `NOAH_LOG_CONSOLE` | `1` | `logs/` に加えてターミナルにも詳細ログを表示。既定は非表示。 |


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

## 作業した後に GitHub へ上げる手順

普段の開発では、以下の順番で作業内容を GitHub に反映します。

### 1. 変更内容を確認する

```bash
git status
```

変更されたファイル、新しく追加されたファイル、まだ Git 管理されていないファイルを確認します。

差分を詳しく見たい場合:

```bash
git diff
```

ステージ済みの差分を見たい場合:

```bash
git diff --staged
```

### 2. 変更をステージする

すべての変更をまとめてコミット対象にする場合:

```bash
git add -A
```

特定のファイルだけを入れる場合:

```bash
git add README.md src/Noah.py
```

もう一度確認します。

```bash
git status
```

`Changes to be committed` に入っているものが、次のコミットに含まれます。

### 3. コミットする

```bash
git commit -m "update Noah behavior and README"
```

コミットメッセージは、あとで見返して内容が分かる名前にします。

例:

```bash
git commit -m "docs: update setup instructions"
git commit -m "feat: add shiritori mode"
git commit -m "fix: adjust initiative suppression"
```

### 4. GitHub に push する

```bash
git push origin main
```

これで GitHub の `main` ブランチに反映されます。

---

## push できない時の対処

### `Password authentication is not supported` と出る

GitHub は Git 操作でアカウントのパスワード認証を受け付けていません。  
SSH 接続を使うのがおすすめです。

SSH のリモート URL に切り替える場合:

```bash
git remote set-url origin git@github.com:lilynac/Project-Noah.git
```

接続確認:

```bash
ssh -T git@github.com
```

成功したら、もう一度 push します。

```bash
git push origin main
```

### `fetch first` / `non-fast-forward` と出る

GitHub 側に、手元にない更新がある状態です。  
まずリモートの変更を取り込んでから push します。

```bash
git pull --rebase origin main
git push origin main
```

### コンフリクトが出た場合

`CONFLICT` と表示されたファイルを開いて、衝突箇所を直します。

コンフリクト箇所には、以下のような印が入ります。

```text
<<<<<<< HEAD
GitHub側または現在の内容
=======
自分のコミット側の内容
>>>>>>> commit-id
```

残したい内容だけに整理して、`<<<<<<<`, `=======`, `>>>>>>>` の行を削除します。

修正後:

```bash
git add README.md
git rebase --continue
```

`git rebase --continue` のあとにエディタが開いたら、コミットメッセージをそのまま保存して閉じます。

vim の場合:

```text
Esc
:wq
Enter
```

その後、push します。

```bash
git push origin main
```

### rebase をやめて元に戻したい場合

途中で分からなくなった場合は、rebase 開始前の状態に戻せます。

```bash
git rebase --abort
```

その後、もう一度状況を確認します。

```bash
git status
```

---

## よく使う Git コマンドまとめ

```bash
# 状態確認
git status

# すべての変更をコミット対象へ
git add -A

# コミット
git commit -m "message"

# GitHubへ反映
git push origin main

# GitHub側の更新を取り込んでから自分のコミットを載せ直す
git pull --rebase origin main

# rebaseの続きを実行
git rebase --continue

# rebaseを中止して元に戻す
git rebase --abort
```

---

## Git に入れるもの・入れないもの

基本的には、以下は Git に入れてよいものです。

- `README.md`
- `src/` 以下のコード
- `requirements.txt`
- `.env.example`
- `db/schema.sql`

以下は、環境や個人情報を含む可能性があるため注意してください。

- `.env`
- `logs/`
- `data/memory/`
- `db/noah.db`

`db/noah.db` は Noah の記憶やローカル状態を含む可能性があります。  
配布用・公開用のリポジトリでは、必要に応じて `.gitignore` に追加してください。

```gitignore
.env
logs/
data/memory/
db/noah.db
```

ただし、現在のリポジトリで `db/noah.db` を意図的に管理している場合は、削除・除外する前にバックアップしてください。

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
