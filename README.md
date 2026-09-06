# OpenCraft

**0.16.0-dev.1 — Developer Preview / Architecture Foundation**

AIと対話しながら共有ワールドを制作するための基盤です。**一般配布版ではありません。**
Canonical World が正本で、MCP・HTTP・Blender・ブラウザーはその境界を守るアダプターです。

## Codexだけ、またはClaude Codeだけで使う

使うクライアントを一つ選んでください。両方のインストールは不要です。
LLMと会話画面は普段使っているクライアントのままです。OpenCraftが別のLLMへ転送したり、
OpenAI / AnthropicのAPIキーを要求したりすることはありません。
選んだクライアント自体のインストール・ログインとPython 3.11以上が必要です。

Codexを使う場合、リポジトリのルートで実行します。

```sh
python scripts/setup_client.py codex
```

Claude Codeを使う場合は、代わりにこちらを実行します。

```sh
python scripts/setup_client.py claude
```

このスクリプトは `.venv` の作成、`.[mcp]` のインストール、非公開ローカルワールドの初期化、
選んだクライアントへのMCP登録を行います。既存のクライアント設定は削除しません。
`--dry-run` なら登録コマンドの表示だけです。Windowsでは `py -3` も使用できます。
登録後、そのクライアントでMCPを再接続して、例えば次のように対話します。

> OpenCraftの現在のワールドと履歴を確認して。港のharbor領域に灯台のエンティティを作る案を出して。
> 既存のものは残して、変更内容をプレビューしてから承認を求めて。

AIは現在の状態を読む → 宣言的な変更案を作る → プレビュー → クライアントの承認フォーム →
一括反映、の順で進めます。「その灯台を少し移動」「直前の施工を取り消して」と続けられます。
**自然言語の解釈は選んだLLMの役割であり、OpenCraft自身に別のチャットモデルは内蔵しません。**

[詳しい設定・診断・制約](docs/NATIVE_CLIENTS.md)を参照してください。

## 現在、実装されていること

| 領域 | 実装状態 |
|---|---|
| ネイティブMCP | stdio通信、6ツール、読み取り専用モード、クライアントをまたがない承認、2つのクライアント設定プロファイル |
| 永続ワールド | SQLite、エンティティ作成・更新・削除、リビジョン、操作履歴、再起動後の復元 |
| 安全な変更 | プレビューに結び付いた単回承認、承認後の再検証、冪等な再試行、保守的なUndo、トランザクション |
| ローカルHTTP | 招待・承認・セッション取消、ワールド状態・イベント取得、同じ永続サービスへのアクセス |
| 基盤・参照実装 | 権限、コンテキスト秘匿化、WebMCP公開ポリシー、Voice状態ポリシー、Blender宣言的Sidecar |

データは既定で `.opencraft-data` に保持します。同じディレクトリを指定すれば、CodexとClaudeで
ワールド状態・施工履歴を共有できます。会話履歴や各クライアントのメモリーを相互転送するものではありません。
両クライアントは同じOSユーザーの権限で動きます。互いに隔離する場合は別ディレクトリを使用してください。

## まだ実装・実証していないこと

`prototype/` はオフラインUXプロトタイプです。MCPで作ったエンティティが自動的にその画面や
Blenderへ描画される実装ではありません。灯台の例も、まずはワールドの構造化データの作成です。

本物のCodex / ClaudeにログインしてLLMを含めた操作を完走する検証、複数ブラウザー／Blenderの
ライブ同期、WebSocket、Cloudflareデプロイ、WebRTC音声、任意アセットの隔離処理、署名済みアプリ配布、
本番用アカウント復旧は未実証です。`terrain.patch` / `semantic.link` は永続サービスでは拒否します。
実装のない処理を成功として返しません。Closed Alpha / General Releaseの許可は引き続きfalseです。

## 開発と検証

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/full_quality_gate.py
python scripts/build_release.py
```

完全な品質ゲートにはNode.js 22とnpmも必要です。Python 3.11 / 3.13、MCP SDK 2.1.1で検証します。
MCPテストは新旧プロトコル、stdio子プロセス、承認拒否、承認状態の改ざん、再起動、再試行を検証します。
これは実クライアントのログインやLLMの理解精度を検証したという意味ではありません。

ソースZIPは品質ゲート通過後にのみ作成し、同じソースからの2回のビルドをCIで比較します。
ローカル認証情報・データベース・私有ワールドをソース配布に含めません。

## 構成とライセンス

- `src/opencraft_server/`: MCP、HTTP、永続ワールド、ローカルワークスペース。
- `src/opencraft_core/` / `src/opencraft_social/`: 正本ポリシーと独立した参照モデル。
- `prototype/` / `webmcp/` / `blender_extension/`: UXと各種アダプターの基礎。

Core、サーバー、文書はApache-2.0。Blender ExtensionはGPL-3.0-or-laterの境界です。
詳細は[LICENSE](LICENSE)、[NOTICE](NOTICE)、[Blenderのライセンス](blender_extension/LICENSE.txt)、
[配布ゲート](product/RELEASE_GATE_JA.md)、[実装状態](docs/REPOSITORY_STATUS.md)を確認してください。
