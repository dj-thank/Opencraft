# OpenCraft

**AIが操作する「Minecraft概念のBlender」**を目指す、オープンな共有3Dワールド基盤です。

人はアバターで永続ワールドへ入り、歩き、話し、場所を指し、AI施工クルーへ依頼します。AIはBlender級の表現力で施工案を作りますが、世界を変更する前にゴーストプレビュー、影響範囲、費用、必要権限を提示し、人間の一回限りの承認を受けます。

> **ワールドが本体。Blenderは制作エンジン。AIは施工クルー。人間は意図・承認・公開を担う。**

[English overview](#english-overview) · [日本語の詳細](README_JA.md) · [Architecture](ARCHITECTURE.md) · [Documentation index](docs/README.md)

## 現在の状態

`0.15.0-dev.1` は **Developer Preview / Architecture Foundation** です。

| 領域 | 現在の状態 |
|---|---|
| ロビーとワールドだけのWorld-first UX | 自己完結ブラウザプロトタイプ実装済み |
| ローカルCanonical World Server | SQLite、HTTP/WebSocket、招待、Session、差分Event、Preview、単回Consent、Atomic Commit、Undoを実装・テスト済み |
| Browser World Client | Bearer認証、一回限りWS Ticket、Resume、Presence、Chunk購読を含む参照Adapter実装済み。UXへの自動接続は未完了 |
| Agent / MCP / WebMCP | 安全境界、参照Gateway、動的Tool Adapter、Schema、テストあり |
| Blender | Extensionと独立Sidecarの参照実装・決定論的ZIPあり。Blender実機・複数台E2Eは未実施 |
| Cloudflare | Durable Objects / SQLite / Hibernationの部分実装。ローカル版との完全パリティと実環境E2Eは未完了 |
| アバター、Voice、空間音響 | UX、ポリシー、Schema、参照モデルあり。実WebRTC / SFU / TURN / Native音響は未接続 |
| 実LLM Provider | 未接続 |
| 署名済みEXE / notarized DMG | 未作成 |

**一般配布版ではありません。** `product/RELEASE_GATE_JA.md` と、品質ゲートが生成する `dist/release-readiness.json` を配布判定の正本にします。

## 90秒で画面を試す

Python 3.11以上を用意します。

```bash
python scripts/build_standalone.py
```

生成された `dist/OpenCraft-World-First-v0.15.html` をブラウザで開きます。

ローカルWebサーバーでPWA版を見る場合:

```bash
python -m http.server 8080 -d prototype
```

- `Enter`: ワールドへ入る
- `WASD`: 移動
- ドラッグ: 視点変更
- `T`: 人間 / Party / Agent共通チャット
- `B`: AI Creative Mode
- `3` または `Alt+A`: Personal Agent
- `Esc`: ワールド上のPause Overlay

この画面体験版は外部通信せず、実際のWebRTC、MCP、Cloudflare、Blender、LLMは呼び出しません。

## ローカル共有サーバーを試す

依存のない参照サーバーは、ソースツリーから直接起動できます。

```bash
# macOS / Linux
./scripts/start-local.sh

# Windows
scripts\start-local.cmd
```

または開発環境を入れて起動します。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
opencraft-server serve --host 127.0.0.1 --port 8787 --data-dir .opencraft-data
```

`http://127.0.0.1:8787/` でプロトタイプを配信します。API契約は [`contracts/server/openapi.json`](contracts/server/openapi.json)、ブラウザ参照実装は [`integration/world-client-adapter.js`](integration/world-client-adapter.js) にあります。

ローカルサーバーは次の境界を実装しています。

```text
Invite / Session
  → Read / Resume / Presence
  → Plan / Preview
  → Preview-bound one-time consent
  → Idempotent atomic commit
  → Provenance / Undo
```

既定で `127.0.0.1` のみに待ち受けます。公開Internetへそのまま露出しないでください。

## 品質ゲート

```bash
pip install -e ".[dev]"
python scripts/run_quality_gate.py
python scripts/build_release.py
```

個別実行:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
npm test
npm run check
```

品質ゲートが失敗した場合、Developer Previewの配布ZIPへ昇格しないFail-closed方式です。

## Agent / WebMCPの原則

```text
Point / Select
  → Intent
  → Privacy-filtered observation
  → Plan
  → Ghost + Diff + Assumptions + Cost
  → Preview-bound, one-time human consent
  → Server-side revalidation
  → Atomic commit
  → Validation + Provenance + Undo
```

WebMCPはブラウザ上の可視ワールドをAgent向けToolへ変換するAdapterです。World Protocol、認証、Voice transport、Blender実行の正本にはしません。

次は公開しません。

- マイクを自動でONにするTool
- 周囲の生音声、Private Chat、Credential、Invite Token
- 任意JavaScript / Python / Shell / Filesystem操作
- Previewと同意なしのWorld Commit

詳しくは [`product/AGENT_WEBMCP_BLUEPRINT_JA.md`](product/AGENT_WEBMCP_BLUEPRINT_JA.md) を参照してください。

## リポジトリ構成

```text
prototype/          World-first UX、Agent Overlay、WebMCP Adapter
src/opencraft_world/ Avatar、Voice、音響、Agent、Policy、MCP参照実装
src/opencraft_server/ SQLite-backed Canonical World Server
integration/        Browser World ClientとNative handoff契約
contracts/server/   OpenAPI、WebSocket、Plan、Capability、Parity契約
blender_extension/  Blender Extensionと独立Sidecar
cloudflare/         Durable Objects参照port（部分パリティ）
launcher/           Desktop Launcher参照実装
packaging/          署名・notarization・配布検証手順
protocols/          Draft 2020-12 JSON Schema
examples/           Schemaに対応する安全なExample
mcp/ / webmcp/      Tool Catalogと境界説明
product/            製品、UX、音響、Blender、運用、配布設計
scripts/            Build、E2E、Fail-closed quality gate
tests/              Python / JavaScript tests
```

## セキュリティ

脆弱性は公開Issueではなく [`SECURITY.md`](SECURITY.md) の手順で報告してください。Developer Previewを重要データの唯一の保存先、公開MCP Gateway、公開World Server、実運用Voiceサービスとして使用しないでください。

## ライセンス

コアはApache License 2.0です。Blender ExtensionはBlenderとの統合境界に合わせ、`blender_extension/LICENSE.txt`に記載したGPL-3.0-or-laterで配布します。第三者SDK、Codec、音響ライブラリ、Avatar素材は同梱しておらず、採用時に個別のライセンスと配布条件を確認します。

---

## English overview

OpenCraft explores an **AI-operated, Minecraft-like persistent world backed by Blender-grade authoring**. Humans navigate, socialize, point at places, and approve changes. Agents inspect bounded context, produce visible previews, and may commit only through capability-scoped, revision-bound, preview-bound, one-time consent.

This repository includes a local SQLite-backed canonical world server, a dependency-free world-first browser prototype, a reference HTTP/WebSocket client adapter, policy and acoustic reference models, JSON Schemas, a reference MCP gateway, a dynamic WebMCP adapter, and a Blender bridge/sidecar reference implementation.

It does **not** yet provide a production Internet-hosted service, proven Cloudflare parity, live WebRTC voice, a real LLM provider, multi-client Blender synchronization, or signed desktop installers. See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`product/RELEASE_GATE_JA.md`](product/RELEASE_GATE_JA.md).
