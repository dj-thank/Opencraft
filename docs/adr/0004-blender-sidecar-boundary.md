# ADR 0004: Blender sidecar boundary

- Status: Accepted
- Date: 2026-09-06

## Context

Blender's Python API is not thread-safe, long-lived background threads can cause instability, and accepting arbitrary generated Python would turn world content into executable code.

## Decision

Networking and untrusted input handling run outside Blender in a local sidecar. The sidecar writes validated, size-limited, declarative messages to a private atomic spool. The Blender extension consumes the spool on Blender's main thread and applies a small allowlist of operations.

Worlds, assets, and agents may not supply executable Python, shell commands, arbitrary file paths, or arbitrary URLs. High-fidelity assets pass a separate quarantine and conversion pipeline before import.

## Consequences

- The Blender extension remains GPL-3.0-or-later and declares files/network permissions.
- Spool schemas are versioned and replay-protected.
- Sidecar and extension are tested independently and together.
- Native executable distribution requires signed installers and clean-machine tests.
