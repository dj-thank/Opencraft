# Governance

OpenCraft is currently maintained by the repository owner with public design and code review through GitHub.

## Decision records

Changes to canonical authority, security boundaries, world format, capability semantics, voice privacy, Blender execution, or release evidence require an Architecture Decision Record under `docs/adr/`.

## Maintainer responsibilities

Maintainers must:

- preserve the canonical-world and least-privilege invariants;
- reject changes that bypass preview, consent, authorization, or provenance;
- keep implementation status and release claims truthful;
- review license compatibility before introducing dependencies or assets;
- avoid merging a large architectural PR while required checks are failing;
- document migration and rollback for persistent-world changes.

## Release authority

A Git tag is not evidence of production readiness. `product/RELEASE_GATE_JA.md` defines the evidence required for Developer Preview, Closed Alpha, and General Release. General Release requires explicit maintainer approval after all blocking evidence is attached.

## Security-sensitive changes

At least one focused review is required for authentication, authorization, capability grants, consent, cryptography, untrusted assets, voice privacy, updater code, and Blender execution boundaries. Self-review alone is not sufficient for General Release.
