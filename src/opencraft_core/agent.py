from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from .canonical import sha256_json


class PlanValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    name: str
    world_id: str
    region_ids: frozenset[str] = frozenset()
    max_operations: int = 100
    max_cost_units: int = 1000

    def allows_region(self, region_id: str | None) -> bool:
        return not self.region_ids or (region_id is not None and region_id in self.region_ids)


@dataclass(frozen=True, slots=True)
class AgentPlan:
    world_id: str
    base_revision: int
    title: str
    operations: tuple[dict[str, Any], ...]
    assumptions: tuple[str, ...] = ()
    cost_units: int = 0
    plan_id: str | None = None

    @property
    def preview_hash(self) -> str:
        return sha256_json({
            "worldId": self.world_id,
            "baseRevision": self.base_revision,
            "title": self.title,
            "operations": self.operations,
            "assumptions": self.assumptions,
            "costUnits": self.cost_units,
        })


_ALLOWED_OPERATIONS = {
    "entity.create", "entity.update", "entity.delete", "terrain.patch", "semantic.link"
}
_PROTECTED_KEYS = {"ownerId", "revision", "worldId", "createdAt", "createdBy"}


def _walk_finite(value: Any, *, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise PlanValidationError(f"non-finite number at {path}")
        if abs(float(value)) > 1_000_000:
            raise PlanValidationError(f"coordinate or scalar outside safety bound at {path}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_finite(child, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_finite(child, path=f"{path}.{key}")
        return
    raise PlanValidationError(f"unsupported value type at {path}")


def validate_agent_plan(plan: AgentPlan, *, grant: CapabilityGrant, current_revision: int,
                        protected_entity_ids: Iterable[str] = ()) -> None:
    if plan.world_id != grant.world_id:
        raise PlanValidationError("plan world does not match grant")
    if plan.base_revision != current_revision:
        raise PlanValidationError("plan was created from a stale world revision")
    if not plan.title.strip() or len(plan.title) > 160:
        raise PlanValidationError("plan title must be 1-160 characters")
    if not plan.operations:
        raise PlanValidationError("plan has no operations")
    if len(plan.operations) > grant.max_operations:
        raise PlanValidationError("operation quota exceeded")
    if plan.cost_units < 0 or plan.cost_units > grant.max_cost_units:
        raise PlanValidationError("cost quota exceeded")

    protected = set(protected_entity_ids)
    for index, operation in enumerate(plan.operations):
        if not isinstance(operation, dict):
            raise PlanValidationError(f"operation {index} must be an object")
        kind = operation.get("kind")
        if kind not in _ALLOWED_OPERATIONS:
            raise PlanValidationError(f"operation {index} has unknown kind")
        region_id = operation.get("regionId")
        if not grant.allows_region(region_id):
            raise PlanValidationError(f"operation {index} is outside the granted region")
        payload = operation.get("payload", {})
        if not isinstance(payload, dict):
            raise PlanValidationError(f"operation {index} payload must be an object")
        if _PROTECTED_KEYS.intersection(payload):
            raise PlanValidationError(f"operation {index} modifies protected fields")
        entity_id = operation.get("entityId")
        if entity_id in protected and kind in {"entity.update", "entity.delete"}:
            raise PlanValidationError(f"operation {index} targets a protected entity")
        _walk_finite(operation, path=f"$.operations[{index}]")
