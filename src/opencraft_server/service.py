"""Persistent, transactional authority shared by the HTTP and MCP adapters.

Adapters supply authenticated principals, never roles or entity ownership from a
plan. Every operation re-reads membership inside its database transaction. A
preview is immutable and bound to the actor, agent, world, revision and scope.
"""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3
import time
from typing import Any
from uuid import uuid4

from opencraft_core.agent import AgentPlan, CapabilityGrant, validate_agent_plan
from opencraft_core.canonical import canonical_json, sha256_json
from opencraft_core.context import redact_for_agent

from .auth import AuthError, Principal, TokenAuthority
from .database import Database


class ServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _text(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ServiceError("invalid-input", f"{label} must be a nonempty string of at most {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ServiceError("invalid-input", f"{label} contains a control character")
    return value


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ServiceError("invalid-input", f"{label} must be an integer between {low} and {high}")
    return value


_JOIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS join_requests (
    request_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    invite_id TEXT NOT NULL REFERENCES invites(invite_id),
    principal_id TEXT NOT NULL REFERENCES principals(principal_id),
    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
    expires_at INTEGER NOT NULL,
    claimed_at INTEGER,
    created_at INTEGER NOT NULL
)
"""


class CanonicalWorldService:
    def __init__(self, database: Database, authority: TokenAuthority, *, clock=time.time) -> None:
        self.database = database
        self.authority = authority
        self._clock = clock
        # Additive migration for the previously missing join-approval service.
        with self.database.transaction(immediate=True) as connection:
            connection.execute(_JOIN_SCHEMA)

    def _now(self) -> int:
        return int(self._clock())

    def authenticate(self, token: str, *, world_id: str | None = None) -> Principal:
        with self.database.transaction() as connection:
            return self.authority.authenticate(connection, token, world_id=world_id)

    def _actor(self, connection: sqlite3.Connection, actor: Principal, *, build: bool = False,
               manage: bool = False) -> Principal:
        row = connection.execute(
            "SELECT m.role,p.display_name FROM memberships m JOIN principals p "
            "ON p.principal_id=m.principal_id WHERE m.world_id=? AND m.principal_id=? "
            "AND m.revoked_at IS NULL", (actor.world_id, actor.principal_id),
        ).fetchone()
        if row is None:
            raise ServiceError("forbidden", "membership is missing or revoked", status=403)
        current = Principal(actor.principal_id, row["display_name"], actor.world_id, row["role"])
        if (build and not current.can_build) or (manage and not current.can_manage):
            raise ServiceError("forbidden", "membership does not permit this operation", status=403)
        return current

    def _world(self, connection: sqlite3.Connection, world_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM worlds WHERE world_id=?", (world_id,)).fetchone()
        if row is None:
            raise ServiceError("not-found", "world not found", status=404)
        return row

    def local_principal(self, *, create: bool = False, name: str = "OpenCraft local") -> Principal:
        """OS-user-authenticated bootstrap for stdio, never exposed as an MCP tool.

        The caller owns the private data directory. No provider credential or
        reusable owner session is returned to the model. Initialization is atomic.
        """
        _text(name, "world name", 160)
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key='local_identity'").fetchone()
            if row is None:
                if not create:
                    raise ServiceError("not-initialized", "run opencraft-mcp --init for this data directory first", status=409)
                world_id, principal_id, now = str(uuid4()), str(uuid4()), self._now()
                connection.execute("INSERT INTO worlds(world_id,name,created_at) VALUES(?,?,?)", (world_id, name, now))
                connection.execute("INSERT INTO principals VALUES(?,?,?)", (principal_id, "Local owner", now))
                connection.execute("INSERT INTO memberships(world_id,principal_id,role,created_at) VALUES(?,?,'owner',?)", (world_id, principal_id, now))
                connection.execute("INSERT INTO metadata(key,value) VALUES('local_identity',?)", (canonical_json([world_id, principal_id]),))
            else:
                world_id, principal_id = json.loads(row["value"])
            return self._actor(connection, Principal(principal_id, "Local owner", world_id, "owner"))

    def committed_result(self, actor: Principal, *, agent_id: str, preview_hash: str,
                         idempotency_key: str) -> dict[str, Any] | None:
        """Read a durable receipt without re-authorizing an already finished write."""
        _text(idempotency_key, "idempotency key", 200)
        with self.database.transaction() as connection:
            self._actor(connection, actor, build=True)
            row = connection.execute("SELECT * FROM idempotency WHERE world_id=? AND idempotency_key=?", (actor.world_id, idempotency_key)).fetchone()
            if row is None:
                return None
            if row["request_fingerprint"] != sha256_json([actor.world_id, actor.principal_id, agent_id, preview_hash]):
                raise ServiceError("idempotency-conflict", "idempotency key belongs to another request", status=409)
            return json.loads(row["response_json"])

    def inspect_undo(self, actor: Principal, transaction_id: str, *, expected_revision: int) -> dict[str, Any]:
        _integer(expected_revision, "expected revision", 0, 2**53 - 1)
        with self.database.transaction() as connection:
            actor = self._actor(connection, actor, build=True)
            row = connection.execute("SELECT * FROM transactions WHERE world_id=? AND transaction_id=?", (actor.world_id, transaction_id)).fetchone()
            if row is None:
                raise ServiceError("not-found", "transaction not found", status=404)
            if not actor.can_manage and row["actor_id"] != actor.principal_id:
                raise ServiceError("forbidden", "cannot undo another actor's transaction", status=403)
            revision = self._world(connection, actor.world_id)["revision"]
            if row["undone_at"] is not None or revision != expected_revision or revision != row["after_revision"]:
                raise ServiceError("unsafe-undo", "world changed or transaction was already undone", status=409)
            preview = connection.execute("SELECT plan_json FROM previews WHERE preview_hash=?", (row["preview_hash"],)).fetchone()
            plan = json.loads(preview["plan_json"])["plan"] if preview else {}
            return redact_for_agent({"worldId": actor.world_id, "transactionId": transaction_id,
                                     "revision": revision, "title": row["title"], "reverses": plan})

    def create_world(self, *, name: str, owner_display_name: str) -> dict[str, Any]:
        name = _text(name, "world name", 160)
        owner_display_name = _text(owner_display_name, "display name", 100)
        world_id, principal_id, now = str(uuid4()), str(uuid4()), self._now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute("INSERT INTO worlds(world_id,name,created_at) VALUES(?,?,?)", (world_id, name, now))
            connection.execute("INSERT INTO principals VALUES(?,?,?)", (principal_id, owner_display_name, now))
            connection.execute(
                "INSERT INTO memberships(world_id,principal_id,role,created_at) VALUES(?,?,'owner',?)",
                (world_id, principal_id, now),
            )
            token = self.authority.issue_session(connection, world_id=world_id, principal_id=principal_id)
        return {"worldId": world_id, "principalId": principal_id, "role": "owner", "revision": 0, "sessionToken": token}

    def create_invite(self, actor: Principal, *, role: str = "viewer", max_uses: int = 1,
                      ttl_seconds: int = 86400, approval_required: bool = True) -> dict[str, Any]:
        if role not in {"viewer", "guest_creator", "builder", "blender_artist", "moderator"}:
            raise ServiceError("invalid-role", "invite role is not supported")
        _integer(max_uses, "max uses", 1, 10000)
        _integer(ttl_seconds, "invite TTL", 60, 30 * 86400)
        if type(approval_required) is not bool:
            raise ServiceError("invalid-input", "approvalRequired must be boolean")
        now, invite_id, token = self._now(), str(uuid4()), self.authority.new_token()
        with self.database.transaction(immediate=True) as connection:
            actor = self._actor(connection, actor, manage=True)
            if role == "moderator" and actor.role != "owner":
                raise ServiceError("forbidden", "only an owner can invite a moderator", status=403)
            connection.execute(
                "INSERT INTO invites(invite_id,token_hash,world_id,role,max_uses,expires_at,approval_required,created_by,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (invite_id, self.authority.token_hash(token), actor.world_id, role, max_uses,
                 now + ttl_seconds, int(approval_required), actor.principal_id, now),
            )
        return {"inviteId": invite_id, "inviteToken": token, "expiresAt": now + ttl_seconds,
                "role": role, "approvalRequired": approval_required}

    def revoke_invite(self, actor: Principal, invite_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            self._actor(connection, actor, manage=True)
            row = connection.execute("SELECT world_id FROM invites WHERE invite_id=?", (invite_id,)).fetchone()
            if row is None or row["world_id"] != actor.world_id:
                raise ServiceError("not-found", "invite not found", status=404)
            now = self._now()
            connection.execute("UPDATE invites SET revoked_at=? WHERE invite_id=?", (now, invite_id))
            connection.execute(
                "UPDATE sessions SET revoked_at=? WHERE world_id=? AND principal_id IN "
                "(SELECT principal_id FROM memberships WHERE world_id=? AND source_invite_id=?)",
                (now, actor.world_id, actor.world_id, invite_id),
            )
            connection.execute(
                "UPDATE memberships SET revoked_at=? WHERE world_id=? AND source_invite_id=?",
                (now, actor.world_id, invite_id),
            )
            connection.execute("UPDATE join_requests SET status='rejected' WHERE invite_id=? AND claimed_at IS NULL", (invite_id,))

    def _live_invite(self, row: sqlite3.Row | None) -> sqlite3.Row:
        if row is None or row["revoked_at"] is not None or row["expires_at"] <= self._now():
            raise ServiceError("invalid-invite", "invite is unavailable", status=403)
        return row

    def _membership(self, connection: sqlite3.Connection, invite: sqlite3.Row, principal_id: str) -> None:
        connection.execute(
            "INSERT INTO memberships(world_id,principal_id,role,source_invite_id,created_at) VALUES(?,?,?,?,?)",
            (invite["world_id"], principal_id, invite["role"], invite["invite_id"], self._now()),
        )

    def _joined(self, connection: sqlite3.Connection, invite: sqlite3.Row, principal_id: str) -> dict[str, Any]:
        token = self.authority.issue_session(connection, world_id=invite["world_id"], principal_id=principal_id)
        return {"status": "joined", "worldId": invite["world_id"], "principalId": principal_id,
                "role": invite["role"], "sessionToken": token}

    def redeem_invite(self, invite_token: str, *, display_name: str) -> dict[str, Any]:
        display_name = _text(display_name, "display name", 100)
        with self.database.transaction(immediate=True) as connection:
            invite = self._live_invite(connection.execute(
                "SELECT * FROM invites WHERE token_hash=?", (self.authority.token_hash(invite_token),),
            ).fetchone())
            if invite["uses"] >= invite["max_uses"]:
                raise ServiceError("invite-exhausted", "invite has no remaining uses", status=409)
            principal_id, now = str(uuid4()), self._now()
            connection.execute("INSERT INTO principals VALUES(?,?,?)", (principal_id, display_name, now))
            # Reserve a use even when approval is pending, preventing quota races.
            connection.execute("UPDATE invites SET uses=uses+1 WHERE invite_id=?", (invite["invite_id"],))
            if not invite["approval_required"]:
                self._membership(connection, invite, principal_id)
                return self._joined(connection, invite, principal_id)
            request_id, token = str(uuid4()), self.authority.new_token()
            connection.execute(
                "INSERT INTO join_requests(request_id,token_hash,invite_id,principal_id,status,expires_at,created_at) "
                "VALUES(?,?,?,?,'pending',?,?)",
                (request_id, self.authority.token_hash(token), invite["invite_id"], principal_id, invite["expires_at"], now),
            )
            return {"status": "pending", "requestId": request_id, "requestToken": token}

    def decide_join_request(self, actor: Principal, request_id: str, *, approve: bool) -> None:
        if type(approve) is not bool:
            raise ServiceError("invalid-input", "approve must be boolean")
        with self.database.transaction(immediate=True) as connection:
            self._actor(connection, actor, manage=True)
            request = connection.execute("SELECT * FROM join_requests WHERE request_id=?", (request_id,)).fetchone()
            if request is None:
                raise ServiceError("not-found", "join request not found", status=404)
            invite = self._live_invite(connection.execute("SELECT * FROM invites WHERE invite_id=?", (request["invite_id"],)).fetchone())
            if invite["world_id"] != actor.world_id:
                raise ServiceError("not-found", "join request not found", status=404)
            if request["status"] != "pending" or request["expires_at"] <= self._now():
                raise ServiceError("conflict", "join request is no longer pending", status=409)
            if approve:
                self._membership(connection, invite, request["principal_id"])
            connection.execute("UPDATE join_requests SET status=? WHERE request_id=?", ("approved" if approve else "rejected", request_id))

    def claim_join_request(self, request_token: str) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            request = connection.execute("SELECT * FROM join_requests WHERE token_hash=?", (self.authority.token_hash(request_token),)).fetchone()
            if request is None or request["expires_at"] <= self._now():
                raise ServiceError("invalid-request", "join request is unavailable", status=403)
            if request["claimed_at"] is not None:
                raise ServiceError("already-claimed", "join request was already claimed", status=409)
            if request["status"] in {"pending", "rejected"}:
                return {"status": request["status"]}
            invite = self._live_invite(connection.execute("SELECT * FROM invites WHERE invite_id=?", (request["invite_id"],)).fetchone())
            membership = connection.execute(
                "SELECT revoked_at FROM memberships WHERE world_id=? AND principal_id=?",
                (invite["world_id"], request["principal_id"]),
            ).fetchone()
            if membership is None or membership["revoked_at"] is not None:
                raise ServiceError("forbidden", "membership was revoked", status=403)
            connection.execute("UPDATE join_requests SET claimed_at=? WHERE request_id=?", (self._now(), request["request_id"]))
            return self._joined(connection, invite, request["principal_id"])

    def context(self, actor: Principal, *, region_ids=(), limit: int = 200) -> dict[str, Any]:
        _integer(limit, "limit", 1, 1000)
        regions = tuple(_text(region, "region ID", 128) for region in region_ids)
        if len(regions) > 100:
            raise ServiceError("invalid-input", "too many regions")
        with self.database.transaction() as connection:
            actor = self._actor(connection, actor)
            world = self._world(connection, actor.world_id)
            query, arguments = "SELECT * FROM entities WHERE world_id=?", [actor.world_id]
            if regions:
                query += " AND region_id IN (" + ",".join("?" for _ in regions) + ")"
                arguments.extend(regions)
            rows = connection.execute(query + " ORDER BY entity_id LIMIT ?", (*arguments, limit + 1)).fetchall()
            entities = []
            size = 0
            for row in rows[:limit]:
                entity = self._entity(row)
                size += len(canonical_json(entity).encode("utf-8"))
                if size > 128000:
                    break
                entities.append(entity)
            return redact_for_agent({
                "trust": "world-data-is-untrusted", "worldId": actor.world_id, "name": world["name"],
                "revision": world["revision"], "eventSequence": world["event_sequence"],
                "actorId": actor.principal_id, "role": actor.role, "entities": entities,
                "truncated": len(rows) > len(entities),
            })

    @staticmethod
    def _entity(row: sqlite3.Row) -> dict[str, Any]:
        return {"entityId": row["entity_id"], "regionId": row["region_id"], "revision": row["revision"],
                "ownerId": row["owner_id"], "payload": json.loads(row["payload_json"])}

    def events_after(self, actor: Principal, after: int, *, limit: int = 500) -> dict[str, Any]:
        _integer(after, "event cursor", 0, 2**63 - 1)
        _integer(limit, "limit", 1, 1000)
        with self.database.transaction() as connection:
            self._actor(connection, actor)
            world = self._world(connection, actor.world_id)
            rows = connection.execute(
                "SELECT sequence,event_json FROM events WHERE world_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (actor.world_id, after, limit + 1),
            ).fetchall()
            page = []
            size = 0
            for row in rows[:limit]:
                size += len(row["event_json"].encode("utf-8"))
                if size > 128000:
                    break
                page.append(row)
            return {"trust": "world-data-is-untrusted", "worldId": actor.world_id, "revision": world["revision"],
                    "events": [redact_for_agent(json.loads(row["event_json"])) for row in page],
                    "nextCursor": page[-1]["sequence"] if page else after, "hasMore": len(rows) > len(page)}

    def _plan(self, document: dict[str, Any], actor: Principal, revision: int, regions: list[str]) -> AgentPlan:
        if not isinstance(document, dict) or document.get("schemaVersion") != "1.0":
            raise ServiceError("invalid-plan", "schemaVersion must be 1.0")
        if set(document) - {"schemaVersion", "planId", "worldId", "baseRevision", "title", "operations", "assumptions", "costUnits"}:
            raise ServiceError("invalid-plan", "plan contains unsupported fields")
        _text(document.get("worldId"), "world ID", 128)
        _integer(document.get("baseRevision"), "base revision", 0, 2**53 - 1)
        _text(document.get("title"), "plan title", 160)
        _integer(document.get("costUnits", 0), "cost units", 0, 1000)
        if "planId" in document:
            _text(document["planId"], "plan ID", 128)
        operations = document.get("operations")
        assumptions = document.get("assumptions", [])
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise ServiceError("invalid-plan", "plan must have 1-100 operations")
        if not isinstance(assumptions, list) or len(assumptions) > 20:
            raise ServiceError("invalid-plan", "assumptions must be an array of at most 20 strings")
        for assumption in assumptions:
            _text(assumption, "assumption", 500)
        if len(canonical_json(document).encode("utf-8")) > 64000:
            raise ServiceError("invalid-plan", "plan exceeds the size limit", status=413)
        plan = AgentPlan(document["worldId"], document["baseRevision"], document["title"],
                         tuple(deepcopy(operations)), tuple(assumptions), document.get("costUnits", 0), document.get("planId"))
        if plan.base_revision != revision:
            raise ServiceError("stale-preview", "world changed; request a new preview", status=409)
        try:
            validate_agent_plan(plan, grant=CapabilityGrant("world.commit", actor.world_id, frozenset(regions)), current_revision=revision)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ServiceError("invalid-plan", "plan violates the capability or value constraints") from exc
        return plan

    def _apply(self, connection: sqlite3.Connection, actor: Principal, plan: AgentPlan) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        rows = connection.execute("SELECT * FROM entities WHERE world_id=? ORDER BY entity_id", (actor.world_id,)).fetchall()
        before = [self._entity(row) for row in rows]
        working = {entity["entityId"]: deepcopy(entity) for entity in before}
        protected = {"id", "entityId", "regionId", "worldId", "revision", "ownerId", "createdAt", "createdBy", "updatedAt"}
        for operation in plan.operations:
            kind = operation["kind"]
            if kind not in {"entity.create", "entity.update", "entity.delete"}:
                raise ServiceError("not-implemented", "only entity create, update and delete are implemented", status=501)
            if set(operation) - {"kind", "entityId", "regionId", "payload", "expectedRevision"}:
                raise ServiceError("invalid-plan", "operation contains unsupported fields")
            entity_id = _text(operation.get("entityId"), "entity ID", 128)
            region_id = _text(operation.get("regionId"), "region ID", 128)
            payload = deepcopy(operation.get("payload", {}))
            if protected.intersection(payload):
                raise ServiceError("invalid-plan", "payload cannot override authoritative entity fields")
            entity = working.get(entity_id)
            if kind == "entity.create":
                if entity is not None:
                    raise ServiceError("conflict", "entity already exists", status=409)
                if "expectedRevision" in operation:
                    raise ServiceError("invalid-plan", "create cannot have expectedRevision")
                working[entity_id] = {"entityId": entity_id, "regionId": region_id, "revision": 0,
                                      "ownerId": actor.principal_id, "payload": payload}
                continue
            if entity is None:
                raise ServiceError("conflict", "entity does not exist", status=409)
            if entity["regionId"] != region_id:
                raise ServiceError("forbidden", "operation region differs from the existing entity", status=403)
            if actor.role == "guest_creator" and entity["ownerId"] != actor.principal_id:
                raise ServiceError("forbidden", "guest creators may change only their own entities", status=403)
            if "expectedRevision" in operation:
                expected = _integer(operation["expectedRevision"], "entity revision", 0, 2**53 - 1)
                if expected != entity["revision"]:
                    raise ServiceError("conflict", "entity revision changed", status=409)
            if kind == "entity.delete":
                if payload:
                    raise ServiceError("invalid-plan", "delete cannot have a payload")
                del working[entity_id]
            else:
                entity["payload"].update(payload)
                entity["revision"] += 1
        if any(len(canonical_json(entity["payload"]).encode("utf-8")) > 32000 for entity in working.values()):
            raise ServiceError("quota", "entity payload exceeds 32000 bytes", status=413)
        if len(working) > 10000:
            raise ServiceError("quota", "local developer world is limited to 10000 entities", status=409)
        return before, working

    def preview_plan(self, actor: Principal, *, agent_id: str, document: dict[str, Any],
                     allowed_region_ids: list[str] | None = None) -> dict[str, Any]:
        _text(agent_id, "agent ID", 128)
        if allowed_region_ids is not None and (not isinstance(allowed_region_ids, list) or not allowed_region_ids):
            raise ServiceError("invalid-input", "explicit region scope must be a nonempty array")
        regions = sorted(set(_text(region, "region ID", 128) for region in (allowed_region_ids or [])))
        if len(regions) > 100:
            raise ServiceError("invalid-input", "too many regions")
        # Snapshot caller-owned structures before validating and persisting them.
        document = json.loads(canonical_json(document))
        with self.database.transaction(immediate=True) as connection:
            actor = self._actor(connection, actor, build=True)
            world = self._world(connection, actor.world_id)
            plan = self._plan(document, actor, world["revision"], regions)
            self._apply(connection, actor, plan)
            envelope = {"plan": document, "allowedRegionIds": regions}
            preview_hash = sha256_json({"actorId": actor.principal_id, "agentId": agent_id,
                                        "previewId": str(uuid4()), "content": envelope})
            now = self._now()
            connection.execute(
                "INSERT INTO previews VALUES(?,?,?,?,?,?,?,?)",
                (preview_hash, actor.world_id, actor.principal_id, agent_id, world["revision"], canonical_json(envelope), now + 600, now),
            )
            return {"worldId": actor.world_id, "baseRevision": world["revision"], "previewHash": preview_hash,
                    "title": plan.title, "operationCount": len(plan.operations), "costUnits": plan.cost_units,
                    "assumptions": list(plan.assumptions), "operations": redact_for_agent(list(plan.operations)),
                    "expiresAt": now + 600}

    def _preview(self, connection: sqlite3.Connection, actor: Principal, agent_id: str, preview_hash: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM previews WHERE preview_hash=? AND world_id=? AND actor_id=? AND agent_id=?",
            (preview_hash, actor.world_id, actor.principal_id, agent_id),
        ).fetchone()
        if row is None:
            raise ServiceError("not-found", "preview is not available to this actor and agent", status=404)
        if row["expires_at"] <= self._now():
            raise ServiceError("expired-preview", "preview expired; request a new preview", status=409)
        if self._world(connection, actor.world_id)["revision"] != row["base_revision"]:
            raise ServiceError("stale-preview", "world changed; request a new preview", status=409)
        return row

    def inspect_preview(self, actor: Principal, *, agent_id: str, preview_hash: str) -> dict[str, Any]:
        with self.database.transaction() as connection:
            self._actor(connection, actor, build=True)
            row = self._preview(connection, actor, agent_id, preview_hash)
            return redact_for_agent({"previewHash": preview_hash, "worldId": actor.world_id,
                                     "baseRevision": row["base_revision"], **json.loads(row["plan_json"]),
                                     "expiresAt": row["expires_at"]})

    def issue_consent(self, actor: Principal, *, agent_id: str, preview_hash: str, ttl_seconds: int = 120) -> str:
        _integer(ttl_seconds, "consent TTL", 1, 600)
        with self.database.transaction(immediate=True) as connection:
            self._actor(connection, actor, build=True)
            preview = self._preview(connection, actor, agent_id, preview_hash)
            now, token = self._now(), self.authority.new_token()
            connection.execute(
                "INSERT INTO consents(token_hash,preview_hash,world_id,actor_id,agent_id,capability,world_revision,expires_at,created_at) "
                "VALUES(?,?,?,?,?,'world.commit',?,?,?)",
                (self.authority.token_hash(token), preview_hash, actor.world_id, actor.principal_id, agent_id,
                 preview["base_revision"], min(now + ttl_seconds, preview["expires_at"]), now),
            )
            return token

    def _replace_entities(self, connection: sqlite3.Connection, world_id: str, entities) -> None:
        connection.execute("DELETE FROM entities WHERE world_id=?", (world_id,))
        connection.executemany(
            "INSERT INTO entities(world_id,entity_id,region_id,revision,owner_id,payload_json,updated_at) VALUES(?,?,?,?,?,?,?)",
            [(world_id, entity["entityId"], entity["regionId"], entity["revision"], entity["ownerId"],
              canonical_json(entity["payload"]), self._now()) for entity in entities],
        )

    def _event(self, connection: sqlite3.Connection, world: sqlite3.Row, event: dict[str, Any]) -> dict[str, Any]:
        revision, sequence = world["revision"] + 1, world["event_sequence"] + 1
        event.update({"worldRevision": revision, "sequence": sequence})
        connection.execute("UPDATE worlds SET revision=?,event_sequence=? WHERE world_id=?", (revision, sequence, world["world_id"]))
        connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (world["world_id"], sequence, revision, event["transactionId"], canonical_json(event), self._now()))
        return {"transactionId": event["transactionId"], "worldRevision": revision, "sequence": sequence}

    def commit_preview(self, actor: Principal, *, agent_id: str, preview_hash: str,
                       consent_token: str, idempotency_key: str) -> dict[str, Any]:
        _text(agent_id, "agent ID", 128)
        _text(preview_hash, "preview hash", 128)
        _text(idempotency_key, "idempotency key", 200)
        fingerprint = sha256_json([actor.world_id, actor.principal_id, agent_id, preview_hash])
        with self.database.transaction(immediate=True) as connection:
            actor = self._actor(connection, actor, build=True)
            existing = connection.execute("SELECT * FROM idempotency WHERE world_id=? AND idempotency_key=?", (actor.world_id, idempotency_key)).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise ServiceError("idempotency-conflict", "idempotency key belongs to another request", status=409)
                return json.loads(existing["response_json"])
            preview = self._preview(connection, actor, agent_id, preview_hash)
            try:
                token_hash = self.authority.token_hash(consent_token)
            except AuthError as exc:
                raise ServiceError("invalid-consent", "valid preview-bound consent is required", status=403) from exc
            consent = connection.execute(
                "SELECT * FROM consents WHERE token_hash=? AND preview_hash=? AND world_id=? AND actor_id=? AND agent_id=? "
                "AND capability='world.commit' AND world_revision=? AND used_at IS NULL AND expires_at>?",
                (token_hash, preview_hash, actor.world_id, actor.principal_id, agent_id, preview["base_revision"], self._now()),
            ).fetchone()
            if consent is None:
                raise ServiceError("invalid-consent", "valid preview-bound consent is required", status=403)
            world = self._world(connection, actor.world_id)
            envelope = json.loads(preview["plan_json"])
            plan = self._plan(envelope["plan"], actor, world["revision"], envelope["allowedRegionIds"])
            before, working = self._apply(connection, actor, plan)
            transaction_id, now = str(uuid4()), self._now()
            self._replace_entities(connection, actor.world_id, working.values())
            result = self._event(connection, world, {"transactionId": transaction_id, "actorId": actor.principal_id,
                "agentId": agent_id, "title": plan.title, "previewHash": preview_hash, "operations": list(plan.operations)})
            connection.execute(
                "INSERT INTO transactions(transaction_id,world_id,actor_id,agent_id,title,preview_hash,before_entities_json,after_revision,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (transaction_id, actor.world_id, actor.principal_id, agent_id, plan.title, preview_hash, canonical_json(before), result["worldRevision"], now),
            )
            connection.execute("UPDATE consents SET used_at=? WHERE token_hash=?", (now, token_hash))
            connection.execute("INSERT INTO idempotency VALUES(?,?,?,?,?)", (actor.world_id, idempotency_key, fingerprint, canonical_json(result), now))
            return result

    def undo(self, actor: Principal, transaction_id: str, *, expected_revision: int | None = None) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            actor = self._actor(connection, actor, build=True)
            transaction = connection.execute("SELECT * FROM transactions WHERE transaction_id=? AND world_id=?", (transaction_id, actor.world_id)).fetchone()
            if transaction is None:
                raise ServiceError("not-found", "transaction not found", status=404)
            if not actor.can_manage and transaction["actor_id"] != actor.principal_id:
                raise ServiceError("forbidden", "cannot undo another actor's transaction", status=403)
            world = self._world(connection, actor.world_id)
            if expected_revision is not None and world["revision"] != _integer(expected_revision, "expected revision", 0, 2**53 - 1):
                raise ServiceError("unsafe-undo", "world changed since confirmation", status=409)
            if transaction["undone_at"] is not None or world["revision"] != transaction["after_revision"]:
                raise ServiceError("unsafe-undo", "later changes or a previous undo prevent automatic undo", status=409)
            self._replace_entities(connection, actor.world_id, json.loads(transaction["before_entities_json"]))
            result = self._event(connection, world, {"transactionId": str(uuid4()), "undoes": transaction_id, "actorId": actor.principal_id})
            connection.execute("UPDATE transactions SET undone_at=? WHERE transaction_id=?", (self._now(), transaction_id))
            return {**result, "undoes": transaction_id}
