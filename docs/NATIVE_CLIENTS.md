# Codex / Claude Code: independent native conversation

Use **one** native client. OpenCraft is a local MCP server, not an LLM relay.
The host provides the model, account, conversation history and approval UI.
OpenCraft does not request, store or forward a provider API key.
The chosen host still requires its own installation, authentication and entitlement.

## Automatic setup

From the repository root, run one command, not both:

```sh
python scripts/setup_client.py codex
# OR
python scripts/setup_client.py claude
```

Python 3.11+ is required. On Windows, `py -3` can replace `python`.
Setup creates `.venv`, installs `.[mcp]`, initializes `.opencraft-data`, and invokes
only the selected CLI's `mcp add`. It needs package-install network access.
`--data-dir /absolute/private/world` selects a different world. `--dry-run` only
prints the registration command; it installs nothing and changes no settings.
An existing MCP entry named `opencraft` is not silently removed or replaced.
Inspect it in the native client's MCP settings and resolve a collision explicitly.
Restart/reconnect MCP in the client after registering. In Claude Code, inspect `/mcp`.

## Manual setup and registration

Create a virtual environment and install the optional SDK:

```sh
python -m venv .venv
# macOS/Linux:
.venv/bin/python -m pip install -e ".[mcp]"
.venv/bin/python -m opencraft_server.mcp --data-dir /absolute/private/world --init
# Windows: use .venv\Scripts\python.exe instead of .venv/bin/python.
```

Use ABSOLUTE paths below. Spaces in paths must be quoted. Never place tokens in args.

```sh
codex mcp add opencraft -- /absolute/Opencraft/.venv/bin/python -m opencraft_server.mcp --data-dir /absolute/private/world --client codex
```

Or, independently:

```sh
claude mcp add --transport stdio --scope local opencraft -- /absolute/Opencraft/.venv/bin/python -m opencraft_server.mcp --data-dir /absolute/private/world --client claude
```

For a Codex client using config files, the equivalent addition is:

```toml
[mcp_servers.opencraft]
command = "/absolute/Opencraft/.venv/bin/python"
args = ["-m", "opencraft_server.mcp", "--data-dir", "/absolute/private/world", "--client", "codex"]
```

For a Claude Code project MCP configuration, the equivalent entry is below.
Merge it with existing entries instead of overwriting the file; enable/trust only
this reviewed server in the native client. Windows paths use escaped backslashes
or forward slashes.

```json
{
  "mcpServers": {
    "opencraft": {
      "command": "/absolute/Opencraft/.venv/bin/python",
      "args": ["-m", "opencraft_server.mcp", "--data-dir", "/absolute/private/world", "--client", "claude"]
    }
  }
}
```

These configurations do not require the other provider's client or API.
Append `--read-only` to the server arguments to expose only context and history.

## Conversation and confirmation

Ask in your normal conversation, for example:

> 現在のOpenCraftワールドを確認し、harbor領域にlighthouseという灯台のエンティティを提案して。
> positionは[1,0,3]。既存のものは消さず、変更内容を見せてから承認を求めて。

The tools read authoritative worldId/revision, preview a declarative plan, request
confirmation, commit atomically, then return transactionId/worldRevision/sequence.
Only `entity.create`, `entity.update`, and `entity.delete` are supported.
A preview is not a completed build. The browser prototype and Blender are not
live renderers of this local MCP workspace yet.

Approval uses the official SDK's resolver-injected boolean form. It is deliberately
absent from the model's input schema. Inspect the exact plan, world, revision and
preview hash in the form. Decline, cancel or an unchecked box never commits.
A host lacking form elicitation support fails closed; do not bypass this by giving
the model a raw consent token or automatically answering forms. Host automation
hooks can answer as the host, so a trusted host/UI configuration remains necessary.
This boundary is not a defense against a malicious local OS user or host.

Keep the same `request_id` for a retry of a committed preview. Durable receipts
survive restart without another mutation. An unfinished approval may expire or
become invalid on server restart. Re-read context and generate a fresh preview;
never replay an old approval against a new world revision.
Undo also asks for confirmation and rejects transactions followed by later edits.

## Persistence and privacy

By default the private directory is `.opencraft-data`. World state, metadata and
operation history persist in SQLite; a local token pepper protects HTTP sessions.
Unix directories must belong to the current OS user with mode 0700, data files
are private, and symlinked workspaces are rejected. On Windows use a directory
whose ACL restricts access to your own account; Unix mode checks do not enforce
Windows ACLs. Back up the directory only to a private destination.

Two clients with the same directory intentionally use the same local owner/world.
Their preview approvals remain client/agent-bound. Separate directories create
separate worlds. Native chat history and memories stay in each host and are not
transferred. World fields are untrusted data and common credential fields are
redacted; do not store secrets in world names, descriptions or arbitrary payloads.
No microphone, raw audio, arbitrary shell, filesystem or Blender Python tool exists.

## Diagnostics and test evidence

```sh
.venv/bin/python -m opencraft_server.mcp --client codex --data-dir /absolute/private/world --doctor
# Substitute --client claude when using Claude Code.
```

The doctor checks only the selected executable, SDK and local workspace. It does
not contact a provider, prove the host's login, or claim a successful native-LLM E2E.
A successful SDK test is distinct from a logged-in Codex/Claude smoke test.

CI runs the real SDK in both automatic/current and legacy protocol modes, including
stdio subprocesses, each client profile, restart, idempotency, undo, missing-form
support, decline/cancel, forged model approval and tampered request state.
The automated approval callbacks in tests are fixtures, not production auto-approval.

Before claiming native-host E2E, record host version, OS, SDK version, exact source
commit, discovery result, preview display, approve/decline/cancel, retry, restart,
undo and one natural-language multi-turn interaction. Do not record provider tokens
or private chats. That logged-in host acceptance matrix remains a release blocker.

## Official configuration and protocol references

Checked 2026-09-06:

- Codex MCP: https://developers.openai.com/codex/mcp/
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Official Python SDK: https://py.sdk.modelcontextprotocol.io/
- Elicitation resolvers: https://py.sdk.modelcontextprotocol.io/handlers/elicitation/
- Authenticated multi-round request state: https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/
