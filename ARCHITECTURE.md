# OpenCraft architecture

## Canonical authority

```text
World clients / Blender / Agents / WebMCP / MCP
                  │
                  ▼
          Canonical World Protocol
                  │
       authorization + revision
       preview + consent + commit
       events + provenance + undo
                  │
        persistence / hosting adapter
```

The canonical world authority—not Blender, a browser, or an agent—decides whether a mutation is valid.

## Planes

- **Control plane:** identity, role, presence, party, block, position, capability, world transactions.
- **Media plane:** WebRTC tracks, SFU forwarding, TURN fallback.
- **Acoustic renderer:** HRTF, attenuation, occlusion, transmission, diffraction, reflections, and clarity protection.
- **Agent plane:** context envelopes, plans, previews, consent requests, tool results, and memory policy.

MCP and WebMCP do not transport real-time voice media.

## Mutation invariant

Every mutation resolves to world and actor identity, capability scope, base revision, deterministic request fingerprint, idempotency key, validated operations, preview-bound consent where required, and transaction/provenance/undo metadata.

## Blender boundary

Blender communicates with a local sidecar. The sidecar handles networking and validates spool messages. Blender applies allowlisted operations on its main thread. No world, asset, or agent may provide executable Python.

## Deployment adapters

The local Python server and Cloudflare implementation must pass the same contract and conformance suite. Missing routes fail explicitly; they never silently claim parity.
