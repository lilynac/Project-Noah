# TROUBLESHOOTING.md

Project Noah で困った時の復旧集です。

通常の開発手順や GitHub への反映手順は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

---

## 起動しても Tray が出ない

System Tray が使えない環境では通常の GUI 起動ができません。

Linux の場合は `DISPLAY` または `WAYLAND_DISPLAY` が設定されているか確認します。

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

ヘッドレス環境では GUI ではなく、必要に応じて `--service` や `--once` を使います。

```bash
python -m src --once test
python -m src --service
```

CI やヘッドレス確認では以下も使えます。

```bash
NOAH_NO_DIALOG=1 timeout 8s python -m src || true
```

---

## `Address already in use` / 8765 番ポートが使われている

Noah の HTTP IPC は `127.0.0.1:8765` を使います。すでに別プロセスが使っていると起動に失敗します。

macOS / Linux:

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

Windows PowerShell:

```powershell
netstat -ano | findstr :8765
taskkill /PID <PID> /F
```

---

## 二重起動できない / lock が残っている

`NOAH_LOCK_FILE` に指定された lock file が残っていると、二重起動防止のため起動が止まることがあります。

既定では以下です。

```text
run/noah.lock
run/noah.pid
```

Noah がすでに終了していることを確認してから削除します。

```bash
rm -f run/noah.lock run/noah.pid
```

---

## 返事が返らない / API エラーになる

まず `.env` に `OPENAI_API_KEY` があるか確認します。

```bash
cat .env
```

キーを設定します。

```env
OPENAI_API_KEY=YOUR_KEY_HERE
```

次にログを確認します。

```bash
tail -n 120 logs/noah.errors.log
tail -n 120 logs/ipc.errors.log
tail -n 120 logs/service.log
```

ターミナルにも詳細ログを出したい場合:

```bash
NOAH_LOG_CONSOLE=1 python -m src --once test
```

---

## Overlay に返答が出ない

Overlay は `data/memory/ui_queue.txt` を監視しています。

返答自体が生成されているか確認します。

```bash
tail -n 50 data/memory/ui_queue.txt
```

HTTP IPC 側で返答が出るかも確認します。

```bash
curl -X POST http://127.0.0.1:8765/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"表示テスト"}'
```

GUI 側の問題か、応答生成側の問題かを切り分けます。

---

## 起動演出を止めたい

起動演出を抑えて静かに起動します。

```bash
NOAH_BOOT_STYLE=plain python -m src
```

起動演出の API 生成を使わず、ローカルテンプレートだけにする場合:

```bash
NOAH_BOOT_NARRATION=local python -m src
```

---

## DB を初期化し直したい

開発中に DB を作り直したい場合は、必要に応じてバックアップしてから `db/noah.db` を削除し、再起動します。

```bash
cp db/noah.db db/noah.db.bak
rm db/noah.db
python -m src --once test
```

起動時に `db/schema.sql` から再作成されます。

---

## 記憶・状態ファイルを初期化したい

`data/memory/` には会話履歴、感情状態、抑制状態などが入ります。削除前にバックアップします。

```bash
cp -R data/memory data/memory.bak
```

特定ファイルだけ初期化したい場合の例:

```bash
rm data/memory/conversation_history.json
rm data/memory/suppression.json
rm data/memory/runtime_state.json
```

次回起動時に `bootstrap_once()` が必要なファイルを再作成します。

---

## `Password authentication is not supported` と出る

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

---

## `fetch first` / `non-fast-forward` と出る

GitHub 側に、手元にない更新がある状態です。
まずリモートの変更を取り込んでから push します。

```bash
git pull --rebase origin main
git push origin main
```

---

## コンフリクトが出た場合

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

---

## rebase をやめて元に戻したい

途中で分からなくなった場合は、rebase 開始前の状態に戻せます。

```bash
git rebase --abort
```

その後、もう一度状況を確認します。

```bash
git status
```
