# DEVELOPMENT.md

Project Noah の開発作業メモです。

この資料は、日常的な開発・確認・GitHub への反映手順をまとめます。起動しない、push できない、DB を初期化したいなどの復旧手順は [TROUBLESHOOTING.md](TROUBLESHOOTING.md) を参照してください。

---

## 開発の基本方針

Noah は、デスクトップ常駐、HTTP IPC、記憶、感情状態、自発発話、LLM 呼び出しが同時に動くため、変更時は「小さく切って、1つずつ確認する」方針を優先します。

特に以下は分離して考えます。

- GUI / Tray / Overlay
- HTTP IPC
- 応答生成
- message build
- memory / retrieve
- initiative
- ログ・trace
- ローカル状態ファイル

---

## よく使う起動コマンド

### 通常起動

```bash
python -m src
```

### 1回だけ返答して終了

```bash
python -m src --once こんにちは
```

### HTTP サービスのみ起動

```bash
python -m src --service
```

### 起動演出を抑えて起動

```bash
NOAH_BOOT_STYLE=plain python -m src
```

### 詳細ログをターミナルにも出す

```bash
NOAH_BOOT_VERBOSE=1 NOAH_LOG_CONSOLE=1 python -m src
```

---

## 開発時の確認

### Python 構文チェック

macOS / Linux:

```bash
python -m py_compile $(find src -name '*.py' -not -path './src/legacy/*')
```

Windows PowerShell:

```powershell
Get-ChildItem src -Recurse -Filter *.py |
  Where-Object { $_.FullName -notmatch "legacy" } |
  ForEach-Object { python -m py_compile $_.FullName }
```

### compileall

全体をまとめて確認したい場合:

```bash
python -m compileall -q src
```

### ヘッドレス smoke run

CI やヘッドレス環境では Tray が利用できないことがあるため、`NOAH_NO_DIALOG=1` を使ってダイアログを抑制します。

```bash
NOAH_NO_DIALOG=1 timeout 8s python -m src || true
```

### HTTP IPC の疎通確認

```bash
curl http://127.0.0.1:8765/health
```

会話確認:

```bash
curl -X POST http://127.0.0.1:8765/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"ただいま"}'
```

---

## 作業前の確認

作業前に現在の状態を確認します。

```bash
git status
```

必要に応じて差分を確認します。

```bash
git diff
```

ステージ済みの差分を確認する場合:

```bash
git diff --staged
```

---

## 作業後に GitHub へ上げる手順

### 1. 変更内容を確認する

```bash
git status
```
```bash
git diff
```

### 2. 変更をステージする

すべての変更をまとめてコミット対象にする場合:

```bash
git add -A
```

特定のファイルだけを入れる場合:

```bash
git add README.md docs/ src/Noah.py
```

もう一度確認します。

```bash
git status
```

`Changes to be committed` に入っているものが、次のコミットに含まれます。

### 3. コミットする

```bash
git commit -m ""
```

コミットメッセージは、あとで見返して内容が分かる名前にします。

例:

```bash
git commit -m "docs: update setup instructions"
git commit -m "refactor: split noah runtime modules"
git commit -m "fix: adjust initiative suppression"
git commit -m "feat: add shiritori mode"
```

### 4. GitHub に push する

```bash
git push origin main
```

---

## よく使う Git コマンドまとめ

```bash
# 状態確認
git status

# 差分確認
git diff
git diff --staged

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
- `docs/`
- `src/` 以下のコード
- `requirements.txt`
- `.env.example`
- `db/schema.sql`
- `.github/workflows/`

以下は、環境や個人情報を含む可能性があるため注意します。

- `.env`
- `logs/`
- `data/memory/`
- `data/notes/hidden/`
- `db/noah.db`
- `run/`
- `__pycache__/`
- `.venv/`

推奨 `.gitignore` 例:

```gitignore
.env
.venv/
__pycache__/
*.pyc
logs/
run/
data/memory/
data/notes/hidden/
db/noah.db
```

`db/noah.db` は Noah の記憶やローカル状態を含む可能性があります。公開用のリポジトリでは、必要に応じて `.gitignore` に追加してください。

現在のリポジトリで `db/noah.db` を意図的に管理している場合は、削除・除外する前にバックアップします。

---

## ドキュメント更新ルール

README は初見の入口として短く保ちます。

詳細は以下へ分けます。

- 開発・Git 通常手順: `docs/DEVELOPMENT.md`
- トラブル復旧: `docs/TROUBLESHOOTING.md`
- 内部設計: `docs/ARCHITECTURE.md`
- 環境変数: `docs/CONFIG.md`

README に詳細手順を追加したくなった場合は、まず `docs/` 側に置けないか確認します。
