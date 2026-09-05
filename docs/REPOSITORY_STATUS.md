# Repository status — 0.16.0-dev.1

## Implemented and testable in this repository

- Canonical in-memory world reference model
- Bounded Agent Plan validation
- Privacy-filtered context envelopes
- Preview hashing and single-use consent
- Idempotent commit and conservative undo
- Least-privilege WebMCP tool publication
- MCP 2026-07-28 discovery/header reference checks
- Lobby/world-only shell policy
- Voice capture/listening/agent/recording consent policy
- Blender declarative sidecar and allowlisted proxy application boundary
- JSON Schema examples and local quality scripts

## UX prototype only

- Minecraft-like world-first browser interface
- Agent, build, social, voice, avatar, map, and pause overlays
- Ghost-preview interaction

A prototype interaction is not proof of a connected backend or multiplayer system.

## Partial adapters

- Local canonical server adapter
- Cloudflare Workers / Durable Objects adapter
- Browser world-client adapter
- Blender Extension and sidecar
- MCP Gateway and WebMCP browser adapter

Each adapter must pass the same conformance tests before parity is claimed.

## Not production implemented or verified

- Hosted multi-tenant identity and account recovery
- Live Cloudflare staging parity
- Two-browser world E2E
- Two-Blender-instance E2E
- WebRTC voice, SFU, TURN, spatial acoustics runtime
- Real LLM provider and adversarial evaluation
- Untrusted asset sandbox
- Signed Windows and notarized macOS distribution
- General-release operations, moderation, incident response, and independent review
