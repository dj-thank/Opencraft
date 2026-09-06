# ADR 0002: Preview-bound, single-use consent

- Status: Accepted
- Date: 2026-09-06

## Context

Natural-language intent is ambiguous and agent plans may change after observation, retry, or world updates. A generic “allow this agent” switch cannot safely authorize a destructive world mutation.

## Decision

A commit requiring human approval is authorized only by a short-lived token bound to the actor, agent, world, capability, exact preview hash, and world revision. The token is single-use. The server revalidates the plan, capability, revision, and idempotency key immediately before commit.

The WebMCP `request_commit` tool opens human consent UI; it does not directly mutate the world.

## Consequences

- A consent cannot be reused for another plan, revision, world, actor, or agent.
- Retry safety is handled by idempotency, not by reusing consent.
- Changed plans require a new preview and a new consent.
- Small low-risk actions may receive separately scoped policy grants, but never an unlimited implicit write capability.
