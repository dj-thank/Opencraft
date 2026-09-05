from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
import uuid

from .agent import AgentPlan, CapabilityGrant, validate_agent_plan
from .consent import ConsentStore


class ConflictError(RuntimeError):
    pass


class PermissionDenied(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    role: str


class WorldStore:
    """Deterministic in-memory canonical-world reference model."""

    def __init__(self, world_id: str, *, consent_store: ConsentStore | None = None) -> None:
        self.world_id = world_id
        self.revision = 0
        self.entities: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.transactions: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        self.consent_store = consent_store or ConsentStore()

    def preview(self, plan: AgentPlan, *, actor: Actor, grant: CapabilityGrant) -> dict[str, Any]:
        if actor.role not in {"builder", "moderator", "owner"}:
            raise PermissionDenied("actor cannot preview world changes")
        validate_agent_plan(plan, grant=grant, current_revision=self.revision)
        return {
            "worldId": self.world_id,
            "baseRevision": self.revision,
            "previewHash": plan.preview_hash,
            "title": plan.title,
            "operationCount": len(plan.operations),
            "costUnits": plan.cost_units,
            "assumptions": list(plan.assumptions),
        }

    def issue_commit_consent(self, *, actor: Actor, agent_id: str, preview_hash: str,
                             ttl_seconds: int = 120) -> str:
        if actor.role not in {"builder", "moderator", "owner"}:
            raise PermissionDenied("actor cannot authorize a commit")
        return self.consent_store.issue(
            actor_id=actor.actor_id,
            agent_id=agent_id,
            world_id=self.world_id,
            capability="world.commit",
            preview_hash=preview_hash,
            world_revision=self.revision,
            ttl_seconds=ttl_seconds,
        )

    def commit(self, plan: AgentPlan, *, actor: Actor, agent_id: str,
               grant: CapabilityGrant, consent_token: str,
               idempotency_key: str) -> dict[str, Any]:
        if actor.role not in {"builder", "moderator", "owner"}:
            raise PermissionDenied("actor cannot commit world changes")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("invalid idempotency key")
        fingerprint = plan.preview_hash
        existing = self.idempotency.get(idempotency_key)
        if existing is not None:
            previous_fingerprint, previous_result = existing
            if previous_fingerprint != fingerprint:
                raise ConflictError("idempotency key was reused for different content")
            return deepcopy(previous_result)

        validate_agent_plan(plan, grant=grant, current_revision=self.revision)
        self.consent_store.consume(
            consent_token,
            actor_id=actor.actor_id,
            agent_id=agent_id,
            world_id=self.world_id,
            capability="world.commit",
            preview_hash=plan.preview_hash,
            world_revision=self.revision,
        )

        before = deepcopy(self.entities)
        working = deepcopy(self.entities)
        for operation in plan.operations:
            kind = operation["kind"]
            entity_id = operation.get("entityId")
            payload = deepcopy(operation.get("payload", {}))
            if kind == "entity.create":
                entity_id = entity_id or str(uuid.uuid4())
                if entity_id in working:
                    raise ConflictError(f"entity already exists: {entity_id}")
                working[entity_id] = {"id": entity_id, **payload}
            elif kind == "entity.update":
                if not entity_id or entity_id not in working:
                    raise ConflictError(f"entity does not exist: {entity_id}")
                expected = operation.get("expectedRevision")
                current = int(working[entity_id].get("revision", 0))
                if expected is not None and int(expected) != current:
                    raise ConflictError(f"stale entity revision: {entity_id}")
                working[entity_id].update(payload)
                working[entity_id]["revision"] = current + 1
            elif kind == "entity.delete":
                if not entity_id or entity_id not in working:
                    raise ConflictError(f"entity does not exist: {entity_id}")
                del working[entity_id]
            elif kind in {"terrain.patch", "semantic.link"}:
                pass

        self.revision += 1
        transaction_id = str(uuid.uuid4())
        event = {
            "sequence": len(self.events) + 1,
            "worldRevision": self.revision,
            "transactionId": transaction_id,
            "actorId": actor.actor_id,
            "agentId": agent_id,
            "title": plan.title,
            "previewHash": plan.preview_hash,
            "operations": deepcopy(plan.operations),
        }
        self.entities = working
        self.events.append(event)
        self.transactions[transaction_id] = {
            "before": before,
            "afterRevision": self.revision,
            "actorId": actor.actor_id,
            "undone": False,
        }
        result = {"transactionId": transaction_id, "worldRevision": self.revision,
                  "sequence": event["sequence"]}
        self.idempotency[idempotency_key] = (fingerprint, deepcopy(result))
        return result

    def undo(self, transaction_id: str, *, actor: Actor) -> dict[str, Any]:
        transaction = self.transactions.get(transaction_id)
        if transaction is None:
            raise ConflictError("unknown transaction")
        if transaction["undone"]:
            raise ConflictError("transaction already undone")
        if actor.role not in {"moderator", "owner"} and actor.actor_id != transaction["actorId"]:
            raise PermissionDenied("actor cannot undo this transaction")
        if self.revision != transaction["afterRevision"]:
            raise ConflictError("later changes prevent a safe automatic undo")
        self.entities = deepcopy(transaction["before"])
        self.revision += 1
        transaction["undone"] = True
        event = {
            "sequence": len(self.events) + 1,
            "worldRevision": self.revision,
            "transactionId": str(uuid.uuid4()),
            "undoes": transaction_id,
            "actorId": actor.actor_id,
        }
        self.events.append(event)
        return {"transactionId": event["transactionId"], "worldRevision": self.revision,
                "sequence": event["sequence"]}
