# Noah (No Alternative Heart)

Mac のメニューバー常駐で使う Noah（常駐MVP）。

## いちばん大事（毎日の使い方）

### 起動
1. 仮想環境を有効化
   source .venv/bin/activate
メニューバー起動

python -m src.noah_menubar
メニューバーの Start を押す
表示が Noah · Ready になったら準備OK

会話
メニューバーの Talk... から送信

終了
メニューバーの Stop → Quit

セットアップ（初回のみ）
Requirements
macOS

Python 3.10+（推奨 3.11〜3.13）

OpenAI API Key

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


開発メモ（Sprint 1の最小受け入れ）
20往復耐久：クラッシュなし
通信障害（APIキー無効）：沈黙せず代替応答、落ちない

