from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = "2026-07-28"


def discover_response(*, server_name: str = "opencraft-reference", version: str = "0.16.0-dev.1") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": "discover",
        "result": {
            "resultType": "complete",
            "protocolVersions": [PROTOCOL_VERSION],
            "serverInfo": {"name": server_name, "version": version},
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": False, "listChanged": True},
                "cancellation": {},
            },
            "ttlMs": 300000,
            "cacheScope": "private",
        },
    }


def validate_transport_headers(headers: dict[str, str], *, method: str, name: str | None = None) -> None:
    lowered = {key.lower(): value for key, value in headers.items()}
    if lowered.get("mcp-protocol-version") != PROTOCOL_VERSION:
        raise ValueError("unsupported MCP protocol version")
    if lowered.get("mcp-method") != method:
        raise ValueError("Mcp-Method does not match request")
    if name is not None and lowered.get("mcp-name") != name:
        raise ValueError("Mcp-Name does not match request")
