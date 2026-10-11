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

### 自動テスト（API キー不要）

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

感情モデル・応答文の整形・HTTP IPC の入力検証を確認します。
PyQt6 がインストールされている場合はチャット画面の送信・エラー復旧・再表示も
画面表示なしで検証します。未インストールの場合は GUI テストのみスキップします。IPC テストは
応答生成を置き換えて一時的な localhost ポートを使うため、OpenAI API の呼び出しや
個人の記憶ファイルの読み書きは行いません。テストだけなら `requirements.txt` の
インストールは不要です。

GitHub Actions の `tests` ワークフローでも、Python 3.12 を使って
Linux / Windows / macOS でテストと構文チェックを実行します。

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

## 開発ログとテーマ別ストーリー

複数段階にわたる機能開発、設計変更、障害対応では、着手時に目的・利用者・確認可能な完了条件・制約を定めます。作業ツリーの開始状態と対象範囲も確認し、変更前からある内容を今回の成果へ混ぜません。

### 開発ログに残すこと

会話全文ではなく、着手・判断・予定外の問題・確認・終了または中断の節目を短く記録します。短い作業は一つの記録にまとめて構いません。

- 作業の日付、テーマ、関連する依頼・Issue、目的と完了条件。
- AIの提案・作業、人が選択・修正した判断、その理由と判断者。
- 変更したファイル・成果物、PR・コミット等の参照先。
- 実施した確認、その結果・証拠、未確認の範囲。
- 問題の時系列・対象・影響・対応・対応後の確認と、一時変更の後片付け。
- 直接得た利用者のフィードバック、再利用できる知識、残件と次の一手。

本人の報告、ログや成果物で確認した事実、推定、未確認事項を分けます。時刻・影響・原因・成果を根拠なく補わず、分からない項目は「未記録」「未確認」と残します。応急復旧と根本原因の解決、提案・実施済み・検証済み・利用者確認済みを区別します。

今後の公開可能な開発記録は `docs/development-logs/YYYY-MM-DD-topic.md` に保存し、確認した成果物やコミットへリンクします。非公開の作業資料は、Git管理外のチェックアウト内 `outputs/` または、このMacの `/Users/simseat/Codex/Noah-workspace/outputs` に保存します。開発ファイル・生成物・ログ・バックアップはiCloud Drive外に置きます。

### ログからストーリーへ編集する流れ

[テーマ別ストーリー編集室（theme-story-system）](https://github.com/lilynac/theme-story-system) の[要件](https://github.com/lilynac/theme-story-system/blob/main/docs/product-requirements.md)と[データモデル](https://github.com/lilynac/theme-story-system/blob/main/docs/data-model.md)を参照します。

1. 開発ログから出来事・判断・知見ごとの記録カードを作り、日付・テーマ・根拠状態・元記録への参照を付ける。
2. 共通のテーマでカードを束ね、同じ出来事のログ・日報・週報には要約元や関連記録を付ける。要約を独立した別の成果や証拠として数えない。
3. 背景を「起」、取り組みと判断を「承」、新しい発見や方針変更を「転」、確認できた結果・残件・学びを「結」へ配置する。転機がなければ重要な判断や学びを置き、出来事を脚色しない。
4. 記事の各主張からカード・元記録・成果物へ戻れるかを確認する。推定・未確認の状態は記事にも引き継ぎ、因果関係・数値・効果を補わない。
5. AIが分類・文章化した内容は下書きとして扱い、人が根拠と公開範囲を確認してから記事を確定する。公開可能な記事は `docs/stories/topic.md` に保存し、元の開発ログを参照する。

日報・週報も同じ元記録から作ります。記事や報告は編集した成果物として扱い、元記録を上書きしません。テーマ別ストーリー編集室の現行試作は手動のテーマ付け・章への配置・書き出しに対応します。Noahからの自動取り込みやAIによる自動記事生成は、この手順の実装済み機能ではありません。

### 個人データの扱い

Noahの会話履歴、利用者の記憶データ、実行ログは開発記録と別の個人データです。明示的な指示なしに開発ログ・記事・例へコピーしたり、外部の編集サービスへ送ったりしません。認証情報・APIキー・私的な会話は公開用記録へ含めず、既存の保存・除外ルールに従います。

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

今回変更したファイルを指定します。例えば開発手順とREADMEを更新した場合:

```bash
git add docs/DEVELOPMENT.md README.md
```

もう一度確認します。

```bash
git status
```

`Changes to be committed` に入っているものが、次のコミットに含まれます。
既存のステージ済み変更がある場合も、今回の依頼と無関係な内容をコミットに混ぜません。

### 3. コミットする

```bash
git commit -m "docs: update development workflow"
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
git branch -vv
git push
```

`git push` は現在のブランチの設定済みupstreamへ送ります。upstreamがない場合は送信先を確認してから設定します。作業ブランチへのpushだけでは `main` の文書は更新されません。作業ブランチの変更を `main` へ反映する場合はPRの変更範囲を確認してマージし、GitHubの `main` に対象の文書があることまで確認します。

---

## よく使う Git コマンドまとめ

```bash
# 状態確認
git status

# 差分確認
git diff
git diff --staged

# 今回のファイルをコミット対象へ
git add docs/DEVELOPMENT.md README.md

# コミット
git commit -m "message"

# 設定済みupstreamへ反映
git branch -vv
git push

# 作業ツリーがcleanでupstreamがある場合の同期
git pull --ff-only
```

既存変更や未追跡ファイルがある場合は同期を見送り、状態を保全します。履歴の分岐や接続失敗で同期できない場合は理由を記録し、最新のリモート状態を取得できたとは扱いません。

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
