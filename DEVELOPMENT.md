# Development guide

## Supported toolchain

- Python 3.11–3.13
- Node.js 22+
- Blender 4.2+ for extension integration work

## Fast path

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/run_quality_gate.py
npm run quality
```

## Source layout

- `src/opencraft_core`: canonical policy, transaction, consent, context, and MCP/WebMCP reference logic
- `src/opencraft_server`: local canonical world server adapter
- `src/opencraft_social`: world-first shell and voice-state policy model
- `prototype`: dependency-free world-first UX prototype
- `webmcp`: browser tool adapter and catalog
- `mcp`: MCP server catalog and transport notes
- `blender_extension`: Blender 4.2+ extension and sidecar boundary
- `cloudflare`: deployment adapter; never the canonical domain model

## Definition of done

A change is not complete until the invariant is explicit, tests cover success and denial paths, cancellation and retry are defined, no secret-bearing data is logged or cached, migration impact is documented, and the quality gate passes.
