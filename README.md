# Noah (No Alternative Heart)


## 毎日の使い方

### 起動
1. 仮想環境を有効化
   source .venv/bin/activate

2. 起動（標準：Qt / Tray）
   python -m src

- 起動するとトレイ（メニューバー）にアイコンが出ます
- Tray（System Tray）が利用できない環境では警告を表示して終了します
- HTTP service は http://127.0.0.1:8765 で待ち受けます（ログに表示）

#### 注意（Qt / Tray）
- このプロジェクトの標準起動は `python -m src`（PyQt6 / QSystemTrayIcon）です。
- デスクトップ環境によっては System Tray が利用できない場合があります。その場合 Noah はクラッシュせず警告を出し、Trayは表示されません（環境側の対応が必要です）。
- 自発発話や Talk… の反応は、Overlay（画面上の Noah）に表示されます。反応が見えないときは `data/memory/ui_queue.txt` を確認してください。


### 終了
- トレイメニューから終了（またはアプリ終了）

### 旧メニューバー（rumps）起動（legacy / 任意）
※ rumps を入れている場合のみ使用できます。通常の起動は `python -m src` です。

python -m src.legacy.noah_menubar

1) 仮想環境
python -m venv .venv
source .venv/bin/activate

2) 依存関係のインストール
pip install -U pip
pip install -r requirements.txt

3) 環境変数（APIキー）
プロジェクト直下に .env を作り、以下を設定：

OPENAI_API_KEY=YOUR_KEY_HERE
ログ/保存先
メニューバー（バックエンド）ログ
~/Library/Logs/Noah/menubar_backend.log

トラブルシューティング
Q. StartしてもReadyにならない / 返事が返らない
まずログを見る：

tail -n 120 ~/Library/Logs/Noah/menubar_backend.log
service が生きているか確認：

curl http://127.0.0.1:8765/health
Q. Address already in use（ポートが使用中）
8765 を掴んでいるプロセスを確認：

lsof -nP -iTCP:8765 -sTCP:LISTEN
PID を止める：

kill <PID>
（例：PIDが 39036 のとき）

kill 39036
強制終了が必要なら：

kill -9 <PID>

