from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worlds (
  world_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
  event_sequence INTEGER NOT NULL DEFAULT 0 CHECK (event_sequence >= 0),
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS principals (
  principal_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('viewer','guest_creator','builder','blender_artist','moderator','owner')),
  source_invite_id TEXT,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, principal_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  session_hash TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_world_principal ON sessions(world_id, principal_id);

CREATE TABLE IF NOT EXISTS invites (
  invite_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('viewer','guest_creator','builder','blender_artist','moderator')),
  max_uses INTEGER NOT NULL CHECK (max_uses >= 1),
  uses INTEGER NOT NULL DEFAULT 0 CHECK (uses >= 0),
  expires_at INTEGER NOT NULL,
  approval_required INTEGER NOT NULL DEFAULT 0 CHECK (approval_required IN (0,1)),
  revoked_at INTEGER,
  created_by TEXT NOT NULL REFERENCES principals(principal_id),
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  entity_id TEXT NOT NULL,
  region_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK (revision >= 0),
  owner_id TEXT NOT NULL REFERENCES principals(principal_id),
  payload_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, entity_id)
);
CREATE INDEX IF NOT EXISTS entities_region ON entities(world_id, region_id);

CREATE TABLE IF NOT EXISTS previews (
  preview_hash TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  actor_id TEXT NOT NULL REFERENCES principals(principal_id),
  agent_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL,
  plan_json TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS previews_expiry ON previews(expires_at);

CREATE TABLE IF NOT EXISTS consents (
  token_hash TEXT PRIMARY KEY,
  preview_hash TEXT NOT NULL REFERENCES previews(preview_hash) ON DELETE CASCADE,
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  actor_id TEXT NOT NULL REFERENCES principals(principal_id),
  agent_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  world_revision INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS transactions (
  transaction_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  actor_id TEXT NOT NULL REFERENCES principals(principal_id),
  agent_id TEXT NOT NULL,
  title TEXT NOT NULL,
  preview_hash TEXT NOT NULL,
  before_entities_json TEXT NOT NULL,
  after_revision INTEGER NOT NULL,
  undone_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS transactions_world_revision ON transactions(world_id, after_revision);

CREATE TABLE IF NOT EXISTS events (
  world_id TEXT NOT NULL REFERENCES worlds(world_id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  world_revision INTEGER NOT NULL,
  transaction_id TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, sequence)
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version','1') "
                "ON CONFLICT(key) DO NOTHING"
            )

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def integrity_check(self) -> str:
        with closing(self.connect()) as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return str(row[0]) if row else "unknown"
