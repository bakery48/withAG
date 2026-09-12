# withAG

PC で動いている **Antigravity** を、同じ Wi-Fi にいるスマホから擬似的なチャットアプリとして使うためのブリッジです。

```
スマホ(ブラウザ)  ──送信──▶  withAG サーバ(PC)  ──ウィンドウ操作──▶  Antigravity のチャット欄
       ▲                                                                    │
       └────WebSocket で差分配信────  Conversation.md を監視  ◀──書き出し────┘
```

- スマホ側に入れるものはありません（ブラウザで PC の URL を開くだけ）。
- 送信は「Antigravity のウィンドウを前面化 → チャット欄にテキストを入力 → 送信キー」を自動で行います。
- 受信は `Conversation.md` を常時監視し、**増えた分だけ**をスマホへ流します（応答中は逐次表示）。

---

## 1. 必要なもの

| | |
|---|---|
| PC | Windows 10/11、Python 3.10 以上、Antigravity |
| スマホ | PC と同じ Wi-Fi につながっていること。ブラウザだけでOK |

> Python は [python.org](https://www.python.org/downloads/) のインストーラで入れる際、
> 「Add python.exe to PATH」にチェックを入れてください。
> Python 3.10 では TOML の読み込みに `tomli` が必要ですが、`run.bat` が自動で入れます。

## 2. セットアップ

```powershell
git clone <このリポジトリ> withAG
cd withAG
copy config.example.toml config.toml
```

`config.toml` を開いて、最低限この 2 つを直します。

```toml
[server]
token = "自分で決めた推測されにくい文字列"

[watch]
path = 'C:\Users\baker\AppData\Roaming\Antigravity\yun\Conversation.md'
```

あとは `run.bat` をダブルクリックするだけです（初回は仮想環境の作成と
`pip install` が自動で走ります）。

PowerShell から起動する場合は、カレントディレクトリのものを実行するために
`.\` が必要です。

```powershell
.\run.bat
```

起動するとコンソールに次のように出ます。

```
======================================================================
  withAG 起動しました
  スマホでこの URL を開いてください: http://192.168.0.12:8765/?token=xxxxx
  監視対象: C:\Users\baker\AppData\Roaming\Antigravity\yun\Conversation.md
======================================================================
```

手動で動かす場合:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

### Windows ファイアウォール

初回起動時に「アクセスを許可しますか？」と聞かれたら、**プライベートネットワーク**に
チェックを入れて許可してください。許可しそびれた場合は、管理者権限の PowerShell で:

```powershell
New-NetFirewallRule -DisplayName "withAG" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

## 3. スマホからの使い方

1. コンソールに出た URL をスマホのブラウザで開く（QR 化しておくと楽です）。
2. 一度開けば token はブラウザに保存されるので、次からは `http://192.168.0.12:8765/` だけでOK。
3. ホーム画面に追加しておくとアプリのように起動できます。
4. 下の入力欄に書いて ➤ を押すと、PC の Antigravity に打ち込まれて送信されます。
5. Antigravity が応答を書き始めると、そのまま画面に流れてきます。

画面右上の ⓘ で、Antigravity を検出できているか・監視ファイルがあるかを確認できます。

## 4. 送信がうまくいかない時（ここが一番のキモ）

送信は「ウィンドウを前面化 → チャット欄にフォーカス → 貼り付け → 送信キー」という
手順を再現しています。環境によってショートカットが違うので、`config.toml` の
`[antigravity]` を調整してください。

まず単体で試せるツールがあります（スマホ不要）。

```powershell
.venv\Scripts\python tools\try_send.py "テスト送信"
```

### ウィンドウが見つからない

```powershell
.venv\Scripts\python tools\list_windows.py
```

で一覧を出し、Antigravity のウィンドウタイトルに共通して含まれる文字列を
`window_title` に設定します（部分一致・大文字小文字は無視）。

### チャット欄にフォーカスが当たらない

`focus_chat_hotkey` に、Antigravity 側で「チャット欄にカーソルを移す」ショートカットを
設定します。Antigravity のキーボードショートカット設定画面で、チャット / エージェント
パネルを開くコマンドに割り当てられているキーを確認してください。

うまい割り当てが見つからない場合は

```toml
focus_chat_hotkey = ""
```

にして、**Antigravity のチャット欄をクリックした状態で放置**しておく運用でも動きます
（前面化した時点でカーソルが入力欄に残っているため）。

### 文字が途中までしか入らない / 入るのが早すぎる

各待ち時間を増やしてください。

```toml
focus_window_delay_ms = 600
focus_chat_delay_ms = 500
after_input_delay_ms = 300
```

### 送信されない（改行されるだけ / 逆に途中で送信される）

`submit_key` を変えます。`"enter"` / `"ctrl+enter"` / `"shift+enter"` など。

### 日本語が化ける

`input_method = "paste"`（既定）を使ってください。クリップボード経由なので IME の
影響を受けません。`"type"` は 1 文字ずつ Unicode を直接流し込む方式で、
クリップボードを汚したくない場合の代替です。

## 5. 受信がうまくいかない時

- ⓘ パネルで「ファイル: なし」なら `[watch] path` が違います。
- 発言の区切りがおかしい場合、`Conversation.md` の見出し形式が想定と違う可能性があります。
  `server/parser.py` の `USER_WORDS` / `AI_WORDS` に、実際のファイルで使われている
  見出し語を足してください（`## User` `**Assistant:**` `### ユーザー` などは対応済み）。
- 応答の途中で細切れに通知される場合は `settle_ms` を大きく（例: 3000）してください。
  「最後の更新から何 ms 静かなら 1 応答完了と見なすか」の値です。

## 6. スマホのブラウザを閉じていても通知を受け取る

ブラウザを開いている間は音・バイブ・ブラウザ通知で分かりますが、閉じていると届きません。
その場合は [ntfy](https://ntfy.sh/) を併用します。

1. スマホに ntfy アプリを入れる
2. 推測されにくいトピック名（例: `withag-8f2c1d9a`）を購読する
3. `config.toml` を設定して再起動

```toml
[notify]
enabled = true
topic = "withag-8f2c1d9a"
```

`POST /api/notify/test` で疎通確認できます。トピック名を知っている人は誰でも
購読できてしまうので、必ずランダムな文字列にしてください。

## 7. 設定項目

`config.example.toml` にすべてコメント付きで書いてあります。主なものだけ:

| キー | 意味 |
|---|---|
| `server.token` | スマホからの接続に必要な合言葉。必ず変更する |
| `server.port` | 待ち受けポート（既定 8765） |
| `server.ssl_certfile` / `ssl_keyfile` | HTTPS 化する場合に指定 |
| `watch.path` | 監視する `Conversation.md` のフルパス |
| `watch.settle_ms` | 何 ms 静かなら 1 応答完了と見なすか |
| `watch.load_existing_on_start` | 起動時に既存の中身も配信するか |
| `antigravity.window_title` | ウィンドウタイトルの部分一致文字列 |
| `antigravity.focus_chat_hotkey` | チャット欄へフォーカスするショートカット |
| `antigravity.submit_key` | 送信キー |
| `antigravity.input_method` | `paste`（推奨） / `type` |
| `notify.*` | ntfy によるプッシュ通知 |

## 8. セキュリティについて

- 同じ Wi-Fi にいる端末からは誰でも到達できるため、`token` は必ず変更してください。
  token が無い / 違うリクエストは 401 で弾きます。
- 通信は既定では平文 HTTP です。家庭内 LAN 想定ですが、気になる場合は自己署名証明書を
  作って `ssl_certfile` / `ssl_keyfile` を設定してください。

  ```powershell
  mkdir certs
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -keyout certs\key.pem -out certs\cert.pem -subj "/CN=withag"
  ```

  HTTPS にするとスマホのブラウザ通知 API も使えるようになります
  （自己署名なので初回に警告が出ます）。
- **このサーバをインターネットに直接公開しないでください。** 外から使いたい場合は
  Tailscale などの VPN 越しにアクセスするのが安全です。

## 9. 仕組みと制限

- 送信はキーボード操作のエミュレーションなので、**送信の瞬間だけ Antigravity が前面に来ます**
  （`restore_foreground = true` なら直後に元のウィンドウへ戻します）。
  PC を誰かが操作中に送ると打鍵が混ざる可能性があります。
- PC がスリープしていると届きません。電源設定でスリープを切っておくのが確実です。
- `Conversation.md` はファイル全体を書き換える形でも追記でも動きます
  （追記なら末尾の差分、書き換えなら行単位の差分から追加行を拾います）。
- 送信した内容が `Conversation.md` 側にも user 発言として現れる場合、
  同じ文面は二重表示しないよう除外しています。

## 10. 開発

```powershell
python -m unittest discover -s tests
```

| 場所 | 役割 |
|---|---|
| `server/main.py` | HTTP / WebSocket のエンドポイント |
| `server/win_input.py` | Windows のキー入力・クリップボード・ウィンドウ操作（ctypes のみ） |
| `server/injector.py` | Antigravity への打ち込み手順 |
| `server/watcher.py` | `Conversation.md` のポーリング監視と差分抽出 |
| `server/parser.py` | 差分を発言単位へ切り分け |
| `server/store.py` | 履歴の保存と WebSocket への配信 |
| `web/` | スマホ側の画面 |
| `tools/` | ウィンドウ一覧・送信テスト用の補助スクリプト |
