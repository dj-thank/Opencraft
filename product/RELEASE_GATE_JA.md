# OpenCraft リリースゲート

OpenCraftは、ビルドが成功しただけでは一般配布版へ昇格しません。状態は証跡に基づいて判定します。

## Developer Preview

必須条件:

- ソースがリポジトリ内で再現可能
- Python / JavaScript / JSON Schemaの品質ゲートが成功
- 秘密情報やローカルDB、未審査バイナリを含まない
- READMEが未実装領域を明記
- Agent接続と権限、PreviewとCommit、Voice接続とListeningが分離
- 一般公開サーバーとして安全であると表現しない

## Closed Alpha

Developer Previewに加えて、以下の実環境証跡が必要です。

- Cloudflare stagingのデプロイ・マイグレーション・バックアップ復元
- 2台以上のブラウザでPresence、切断復帰、Preview、Consent、Commit、Undo
- Blender 4.2+を2インスタンス以上で導入・同期・終了・クラッシュ復帰
- Owner本人認証、復旧、Session失効、招待取消
- 実LLM ProviderのPrompt Injection、費用超過、Cancel、遅延結果テスト
- 未信頼Assetの隔離・制限・再エンコード
- プライバシーと削除・Exportの実動作

## General Release

Closed Alphaに加えて、以下を要求します。

- 実WebRTC / SFU / TURNによる複数端末Voice E2E
- Lobby / Spatial / Hybrid切替、Block、Mute、字幕、録音同意の試験
- 署名済みWindows Installerとnotarization済みmacOSアプリ／DMG
- BlenderもPythonもないクリーン端末での導入試験
- 非技術者による観察付きUsability Test
- 独立Security ReviewとPrivacy Review
- 利用規約、Privacy Policy、通報、Moderation、Incident Response
- RPO / RTOを伴う定期Restore Drill
- SBOM、Provenance、署名、再現可能Buildの確認

## 現在の判定

`0.16.0-dev.1`は **Developer Preview / Architecture Foundation** です。

```text
Developer Preview: 審査中
Closed Alpha:       BLOCKED
General Release:    BLOCKED
```

品質ゲートの成功は、Cloudflare、Blender、Voice、LLM、Installerの実環境試験を代替しません。
