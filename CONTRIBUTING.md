# Contributing to OpenCraft

OpenCraft is a pre-alpha research and engineering project. Contributions must preserve four invariants:

1. **The world is canonical.** Blender, MCP, WebMCP, browsers, and agents are adapters.
2. **Connection is not permission.** Reading, previewing, committing, listening, and public speaking are separate capabilities.
3. **Preview is not commit.** Destructive or public changes require revision-bound, preview-bound consent.
4. **Lobby and world are the only primary screens.** Tools appear as temporary overlays.

## Local checks

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python scripts/run_quality_gate.py
npm run quality
```

## Pull requests

- Keep one concern per PR.
- Add or update tests for behavior changes.
- Describe security, privacy, migration, and UX impact.
- Do not claim production readiness without the evidence required by `product/RELEASE_GATE_JA.md`.
- Do not commit keys, tokens, local databases, generated release archives, or private world data.

See `DEVELOPMENT.md`, `SECURITY.md`, and `GOVERNANCE.md`.
