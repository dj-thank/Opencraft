# Security policy

OpenCraft is pre-alpha. Do not expose the reference server, MCP gateway, or Blender sidecar directly to the public Internet.

## Reporting

Report suspected vulnerabilities privately to the repository owner. Do not include real tokens, private world exports, raw voice, or personal data in a public issue.

## Current security boundaries

- Agent connection does not grant world-write, voice-listening, public-chat, or public-voice capabilities.
- World commit requires a preview-bound, revision-bound, single-use consent token.
- MCP and WebMCP request domain operations but do not bypass canonical server authorization.
- Blender execution is isolated behind a sidecar and an allowlisted operation protocol.
- Voice media and MCP traffic are separate planes.

## Unsupported for production

Public hosting, multi-tenant identity, account recovery, untrusted asset ingestion, live voice moderation, and signed desktop distribution are not yet production-ready.
