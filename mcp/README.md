# OpenCraft MCP gateway

The MCP gateway is an adapter over the Canonical World Protocol. It is not a second authorization system and cannot bypass world revision, capability, preview, consent, idempotency, or provenance checks.

Target protocol: `2026-07-28`.

Supported reference concepts:

- `server/discover`
- `tools/list` with pagination and private caching
- `tools/call`
- cancellation
- `input_required` for explicit human decisions
- trace context in `_meta`

Voice media, microphone capture, credentials, arbitrary Python, shell, filesystem access, and raw Blender execution are not MCP tools.

A local development gateway must bind to loopback by default. Public deployment requires real authentication, token rotation, origin checks, request limits, revocation, audit, and an independent security review.
