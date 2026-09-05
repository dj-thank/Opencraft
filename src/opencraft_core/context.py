from __future__ import annotations

from copy import deepcopy
from typing import Any

_SENSITIVE_PARTS = (
    "token", "secret", "password", "authorization", "cookie", "api_key", "apikey", "invite", "session"
)


def redact_for_agent(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            output[key] = "[REDACTED]" if any(part in normalized for part in _SENSITIVE_PARTS) else redact_for_agent(child)
        return output
    if isinstance(value, list):
        return [redact_for_agent(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_agent(item) for item in value)
    return deepcopy(value)


def make_context_envelope(*, world_id: str, revision: int, actor_id: str,
                          selection: dict[str, Any] | None, nearby: list[dict[str, Any]],
                          capabilities: list[str]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "trust": "world-data-is-untrusted",
        "worldId": world_id,
        "revision": revision,
        "actorId": actor_id,
        "selection": redact_for_agent(selection),
        "nearby": redact_for_agent(nearby),
        "capabilities": sorted(set(capabilities)),
    }
