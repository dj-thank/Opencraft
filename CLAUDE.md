# Claude Code entry point

Follow the shared project instructions in AGENTS.md, then README.md and
 docs/NATIVE_CLIENTS.md. Claude Code is sufficient on its own: use
`python scripts/setup_client.py claude`. Do not install or call Codex and do not
request an OpenAI key. Continue the conversation in Claude Code; use the same
canonical MCP service and explicit native approval flow described in AGENTS.md.

Run the full quality gate and preserve all authority, privacy and release gates.
A passing SDK transport test does not establish logged-in Claude/LLM E2E coverage.
