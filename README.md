# Noah (No Alternative Heart)

Project Noah は、OpenAI API を活用したデスクトップ常駐型チャットボットの個人開発プロジェクトです。

Python / PyQt6 を用いたローカル GUI アプリケーションとして開発しており、System Tray から呼び出して会話できることを目標にしています。SQLite による会話履歴や状態管理、localhost HTTP IPC による GUI と応答生成処理の分離など、AI API を利用したアプリケーション設計の学習・検証も目的にしています。

本プロジェクトは現在開発中であり、完成品ではありません。実務で行っている業務効率化・自動化の経験をもとに、API 連携、ローカルアプリ開発、データ永続化、運用しやすい構成設計について学習するために制作しています。

---

## Status

現在はプロトタイプ段階です。

基本的なチャット応答、デスクトップ常駐、ローカルでの状態管理、自発発話、記憶の保存と取り出しを試作しながら、機能整理・リファクタリング・テスト追加を進めています。

---

## Noah の特徴

- PyQt6 による System Tray / Overlay 表示
- OpenAI API による会話応答
- SQLite とローカルファイルによる記憶・状態管理
- localhost HTTP IPC による GUI と応答生成処理の分離
- 感情状態、親密度、記憶、作業モードを反映した返答生成
- 抑制ロジック付きの自発発話
- 起動時の状態に応じた短い起動演出

Noah は「便利な万能助手」というより、**静かにそばにいる常駐型パートナー**として調整されています。

---

## 現在の標準構成

```text
Project-Noah-main/
├── README.md
├── requirements.txt
├── .env.example
├── db/
│   └── schema.sql
├── docs/
│   ├── DEVELOPMENT.md
│   ├── TROUBLESHOOTING.md
│   ├── ARCHITECTURE.md
│   └── CONFIG.md
├── src/
│   ├── __main__.py          # 起動入口: python -m src
│   ├── Noah.py              # 互換用の中心モジュール / 既存APIの集約
│   ├── app.py               # CLI / service 実行系
│   ├── noah_prompts.py      # SYSTEM_CORE_PROMPT など
│   ├── llm_trace.py         # LLM trace ログ
│   ├── conversation_history.py
│   ├── message_builder.py
│   ├── qt_entry.py          # 現在の標準 GUI / Tray 起動
│   ├── service.py           # localhost HTTP IPC
│   ├── bootstrap.py         # data/ と db/ の初期化
│   ├── memory/              # episode / summary / narrative 記憶
│   ├── initiative/          # 自発発話の判断・抑制・生成・runner
│   ├── dialogue/            # 返答テンプレート系
│   └── legacy/              # 旧 rumps メニューバー版
└── .github/workflows/
    └── smoke-linux.yml
```

標準起動は **`python -m src`** です。

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

### 3. `.env` を作る

`.env.example` をコピーして `.env` を作ります。

```bash
cp .env.example .env
```

`.env` に OpenAI API キーを設定します。

```env
OPENAI_API_KEY=YOUR_KEY_HERE
```

環境変数の詳細は [docs/CONFIG.md](docs/CONFIG.md) を参照してください。

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

### 1回だけ返答して終了

```bash
python -m src --once こんにちは
```

### HTTP サービスのみ起動

```bash
python -m src --service
```

Tray を出さず、Noah 本体と HTTP IPC を常駐させます。

---

## HTTP IPC

Noah は localhost の `8765` 番ポートで HTTP IPC を受け付けます。

疎通確認:

```bash
curl http://127.0.0.1:8765/health
```

会話:

```bash
curl -X POST http://127.0.0.1:8765/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"ただいま"}'
```

`/chat` と `/talk` はどちらも利用できます。JSON の入力キーは `message`, `text`, `input` のいずれかに対応しています。

---

## データとログ

初回起動時に `src/bootstrap.py` が必要なファイルを作成します。

```text
data/
├── memory/
│   ├── consults.txt
│   ├── emotional_marks.txt
│   ├── preferences.txt
│   ├── noah_identity.txt
│   ├── noah_state.txt
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

ログは標準では `logs/` に出力されます。

```text
logs/
├── noah.log
├── noah.errors.log
├── ipc.log
├── ipc.errors.log
└── service.log
```

---

## 開発者向け資料

詳しい手順や設計メモは `docs/` に分けています。

- [開発作業の手順書](docs/DEVELOPMENT.md)
- [困った時の復旧集](docs/TROUBLESHOOTING.md)
- [内部設計の説明](docs/ARCHITECTURE.md)
- [環境変数辞書](docs/CONFIG.md)

---

## 旧 rumps 版について

`src/legacy/noah_menubar.py` は旧メニューバー実装です。
現在の標準は PyQt6 版のため、通常は使いません。

旧版を試す場合のみ、別途 `rumps` が必要です。

```bash
python -m src.legacy.noah_menubar
```

README の通常手順・トラブルシューティングは現行の PyQt6 版を前提にしています。
