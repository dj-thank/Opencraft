from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time


class ConsentError(RuntimeError):
    pass


@dataclass(slots=True)
class _Consent:
    actor_id: str
    agent_id: str
    world_id: str
    capability: str
    preview_hash: str
    world_revision: int
    expires_at: float
    used: bool = False


class ConsentStore:
    """Reference implementation of short-lived, single-use consent."""

    def __init__(self, *, secret: bytes | None = None, clock=time.time) -> None:
        self._secret = secret or secrets.token_bytes(32)
        if len(self._secret) < 32:
            raise ValueError("secret must be at least 32 bytes")
        self._clock = clock
        self._records: dict[str, _Consent] = {}

    def _digest(self, token: str) -> str:
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def issue(self, *, actor_id: str, agent_id: str, world_id: str, capability: str,
              preview_hash: str, world_revision: int, ttl_seconds: int = 120) -> str:
        if ttl_seconds < 1 or ttl_seconds > 600:
            raise ValueError("ttl_seconds must be between 1 and 600")
        if world_revision < 0:
            raise ValueError("world_revision must be non-negative")
        token = secrets.token_urlsafe(32)
        self._records[self._digest(token)] = _Consent(
            actor_id=actor_id,
            agent_id=agent_id,
            world_id=world_id,
            capability=capability,
            preview_hash=preview_hash,
            world_revision=world_revision,
            expires_at=self._clock() + ttl_seconds,
        )
        return token

    def consume(self, token: str, *, actor_id: str, agent_id: str, world_id: str,
                capability: str, preview_hash: str, world_revision: int) -> None:
        record = self._records.get(self._digest(token))
        if record is None:
            raise ConsentError("unknown consent")
        if record.used:
            raise ConsentError("consent already used")
        if self._clock() >= record.expires_at:
            raise ConsentError("consent expired")
        expected = (record.actor_id, record.agent_id, record.world_id, record.capability,
                    record.preview_hash, record.world_revision)
        actual = (actor_id, agent_id, world_id, capability, preview_hash, world_revision)
        if not hmac.compare_digest(repr(expected), repr(actual)):
            raise ConsentError("consent binding mismatch")
        record.used = True
