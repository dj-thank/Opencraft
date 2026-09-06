# Repository status — 0.16.0-dev.1

## Implemented and testable

Persistent SQLite CanonicalWorldService, local owner bootstrap, HTTP sessions and
revocable invites, bounded/redacted context, entity create/update/delete, immutable
previews, actor/agent/world/revision-bound single-use consent, atomic commit,
durable idempotency receipts, event cursors, and conservative confirmed Undo.

Independent Codex / Claude Code stdio MCP configurations use the same official
SDK server. Current and legacy SDK protocol tests exercise forms, refusal,
request-state integrity, subprocess transport and restart. A source checkout can
configure either client alone without provider API keys. The host supplies its
own LLM, account, chat history and UI.

The earlier in-memory canonical model, capability/consent policies, WebMCP
publication policy, world-first shell, voice state policy, Blender declarative
sidecar and JSON Schema fixtures remain reference components.

## Prototype / incomplete adapters

`prototype/` is an offline UX prototype, not an automatically connected renderer
of the MCP workspace. `webmcp/` is a browser publication-policy adapter.
`blender_extension/` is a declarative sidecar/proxy boundary, not an independently
verified live two-instance system. Cloudflare hosting and WebSocket replication
are future work, not implemented adapters in this source tree.

## Not verified for production

Logged-in native-client natural-language E2E; real LLM adversarial evaluation;
two-browser world synchronization; two-Blender-instance E2E; hosted identity and
recovery; Cloudflare staging; WebRTC/SFU/TURN; untrusted asset sandbox; signed
Windows and notarized macOS packages; usability studies; independent security and
privacy review. See product/RELEASE_GATE_JA.md. General Release remains forbidden.
