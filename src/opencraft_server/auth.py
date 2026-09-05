from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    display_name: str
    world_id: str
    role: str

    @property
    def can_build(self) -> bool:
        return self.role in {"guest_creator", "builder", "blender_artist", "moderator", "owner"}

    @property
    def can_manage(self) -> bool:
        return self.role in {"moderator", "owner"}


class TokenAuthority:
    def __init__(self, secret: bytes, *, clock=time.time) -> None:
        if len(secret) < 32:
            raise ValueError("token pepper must be at least 32 bytes")
        self._secret = secret
        self._clock = clock

    @classmethod
    def from_data_directory(cls, directory: str | Path) -> "TokenAuthority":
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "token-pepper.bin"
        if path.exists():
            secret = path.read_bytes()
        else:
            secret = secrets.token_bytes(32)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(secret)
                handle.flush()
                os.fsync(handle.fileno())
        if os.name != "nt":
            path.chmod(0o600)
        return cls(secret)

    def token_hash(self, token: str) -> str:
        if not token or len(token) > 4096:
            raise AuthError("invalid token")
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def new_token(self) -> str:
        return secrets.token_urlsafe(32)

    def issue_session(self, connection: sqlite3.Connection, *, world_id: str,
                      principal_id: str, ttl_seconds: int = 3600) -> str:
        if ttl_seconds < 60 or ttl_seconds > 30 * 24 * 3600:
            raise ValueError("session ttl must be between one minute and thirty days")
        now = int(self._clock())
        token = self.new_token()
        connection.execute(
            "INSERT INTO sessions(session_hash,world_id,principal_id,expires_at,revoked_at,created_at) "
            "VALUES(?,?,?,?,NULL,?)",
            (self.token_hash(token), world_id, principal_id, now + ttl_seconds, now),
        )
        return token

    def authenticate(self, connection: sqlite3.Connection, token: str, *, world_id: str | None = None) -> Principal:
        now = int(self._clock())
        row = connection.execute(
            "SELECT s.world_id,s.principal_id,p.display_name,m.role,s.expires_at,s.revoked_at,m.revoked_at AS membership_revoked "
            "FROM sessions s JOIN principals p ON p.principal_id=s.principal_id "
            "JOIN memberships m ON m.world_id=s.world_id AND m.principal_id=s.principal_id "
            "WHERE s.session_hash=?",
            (self.token_hash(token),),
        ).fetchone()
        if row is None:
            raise AuthError("unknown session")
        if row["revoked_at"] is not None or row["membership_revoked"] is not None:
            raise AuthError("session revoked")
        if int(row["expires_at"]) <= now:
            raise AuthError("session expired")
        if world_id is not None and row["world_id"] != world_id:
            raise AuthError("session does not belong to this world")
        return Principal(
            principal_id=row["principal_id"],
            display_name=row["display_name"],
            world_id=row["world_id"],
            role=row["role"],
        )

    def revoke_principal_sessions(self, connection: sqlite3.Connection, *, world_id: str, principal_id: str) -> int:
        now = int(self._clock())
        cursor = connection.execute(
            "UPDATE sessions SET revoked_at=? WHERE world_id=? AND principal_id=? AND revoked_at IS NULL",
            (now, world_id, principal_id),
        )
        return cursor.rowcount
