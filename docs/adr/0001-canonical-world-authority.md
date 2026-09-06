# ADR 0001: Canonical world authority

- Status: Accepted
- Date: 2026-09-06

## Context

OpenCraft has browser, Blender, Cloudflare, MCP, WebMCP, and agent components. Allowing any client or adapter to become authoritative would make authorization, conflict handling, replay, audit, and undo inconsistent.

## Decision

The Canonical World Protocol is the only authority for persistent world mutations. Every adapter submits declarative operations with actor identity, capability scope, base revision, idempotency key, and required consent. The canonical authority validates and commits or rejects the transaction.

Blender is a high-fidelity authoring client, not the database. MCP and WebMCP are tool adapters, not permission systems. Cloudflare and the local Python service are deployment adapters, not separate domain models.

## Consequences

- All adapters require a shared conformance suite.
- Offline work is a branch/patch until published by the canonical authority.
- Clients may optimistically render previews but cannot declare them committed.
- Missing deployment parity must fail explicitly.
