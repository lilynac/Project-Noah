# CONFIG.md

Project Noah の環境変数辞書です。

`.env.example` をコピーして `.env` を作り、必要な値を設定します。

```bash
cp .env.example .env
```

---

## 必須

| 変数 | 例 | 説明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | `sk-...` | OpenAI API キー。Noah の応答生成に使います。 |

`.env` の例:

```env
OPENAI_API_KEY=YOUR_KEY_HERE
```

---

## 起動演出

| 変数 | 既定値 | 例 | 説明 |
| --- | --- | --- | --- |
| `NOAH_BOOT_STYLE` | `poetic` | `poetic` / `plain` | 起動演出を表示するか。`plain` にすると抑制します。 |
| `NOAH_BOOT_NARRATION` | `auto` | `auto` / `local` / `off` | 起動演出を API 生成するか。`auto` は API 可なら生成し、失敗時はローカルテンプレートへ戻ります。 |
| `NOAH_BOOT_MODEL` | `gpt-4o-mini` | `gpt-4o-mini` | 起動演出生成に使うモデル。 |
| `NOAH_BOOT_VERBOSE` | `0` | `1` | `[qt_entry] ...` のような開発用 print を表示します。 |

例:

```bash
NOAH_BOOT_STYLE=plain python -m src
```

```bash
NOAH_BOOT_NARRATION=local python -m src
```

---

## 自発発話 / initiative

| 変数 | 既定値 | 説明 |
| --- | ---: | --- |
| `NOAH_INITIATIVE_PER_HOUR` | `5` | 1時間あたりの自発発話の基準回数。 |
| `NOAH_INITIATIVE_JITTER_SECONDS` | `180` | 自発発話タイミングの揺らぎ秒数。 |
| `NOAH_INITIATIVE_MIN_GAP_SECONDS` | `120` | 自発発話同士の最小間隔。 |
| `NOAH_INITIATIVE_RECENT_USER_SILENCE_SECONDS` | `30` | ユーザー入力直後に自発発話を控える秒数。 |
| `NOAH_INITIATIVE_MUTE_SECONDS` | `1800` | stop signal 後などに自発発話を抑制する秒数。 |
| `NOAH_INITIATIVE_CONVERSATION_BLOCK_SECONDS` | `300` | 会話直後に自発発話を控える秒数。 |

例:

```env
NOAH_INITIATIVE_PER_HOUR=5
NOAH_INITIATIVE_JITTER_SECONDS=180
NOAH_INITIATIVE_MIN_GAP_SECONDS=120
NOAH_INITIATIVE_RECENT_USER_SILENCE_SECONDS=30
NOAH_INITIATIVE_MUTE_SECONDS=1800
NOAH_INITIATIVE_CONVERSATION_BLOCK_SECONDS=300
```

---

## ログ

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `NOAH_LOG_DIR` | `logs` | ログ出力先ディレクトリ。 |
| `NOAH_LOG_LEVEL` | `INFO` | ログレベル。 |
| `NOAH_LOG_MAX_BYTES` | `5242880` | ローテーション前の最大サイズ。 |
| `NOAH_LOG_BACKUP_COUNT` | `5` | ローテーション保持数。 |
| `NOAH_LOG_CONSOLE` | `0` | `1` / `true` / `yes` / `on` でターミナルにもログを出します。 |

例:

```env
NOAH_LOG_DIR=logs
NOAH_LOG_LEVEL=INFO
NOAH_LOG_MAX_BYTES=5242880
NOAH_LOG_BACKUP_COUNT=5
NOAH_LOG_CONSOLE=1
```

---

## 実行管理

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `NOAH_PID_FILE` | `run/noah.pid` | 起動中 PID を保存するファイル。 |
| `NOAH_LOCK_FILE` | `run/noah.lock` | 二重起動防止用 lock file。 |

例:

```env
NOAH_PID_FILE=run/noah.pid
NOAH_LOCK_FILE=run/noah.lock
```

---

## ヘッドレス / CI

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `NOAH_NO_DIALOG` | 未設定 | `1` にすると、GUI ダイアログ表示を抑制します。CI やヘッドレス確認向けです。 |

例:

```bash
NOAH_NO_DIALOG=1 timeout 8s python -m src || true
```

---

## デスクトップ環境

| 変数 | 説明 |
| --- | --- |
| `DISPLAY` | Linux の X11 表示先。 |
| `WAYLAND_DISPLAY` | Linux の Wayland 表示先。 |

Linux で Tray が出ない場合は確認します。

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

---

## `.env` サンプル

```env
OPENAI_API_KEY=YOUR_KEY_HERE

# 起動演出
NOAH_BOOT_STYLE=poetic
NOAH_BOOT_NARRATION=auto
NOAH_BOOT_MODEL=gpt-4o-mini
NOAH_BOOT_VERBOSE=0

# 自発発話
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
NOAH_LOG_CONSOLE=0

# 実行管理
NOAH_PID_FILE=run/noah.pid
NOAH_LOCK_FILE=run/noah.lock

# ヘッドレス・CI向け
NOAH_NO_DIALOG=1
```
