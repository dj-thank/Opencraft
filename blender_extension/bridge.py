from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import bpy

COLLECTION_NAME = "OpenCraft World"
ID_PROPERTY = "opencraft_entity_id"
REVISION_PROPERTY = "opencraft_revision"


class BridgeMessageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedMessage:
    sequence: int
    kind: str
    payload: dict[str, Any]


def _finite_vector(value: Any, *, size: int, name: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != size:
        raise BridgeMessageError(f"{name} must be a {size}-element array")
    vector = tuple(float(item) for item in value)
    if not all(math.isfinite(item) and abs(item) <= 1_000_000 for item in vector):
        raise BridgeMessageError(f"{name} contains an unsafe scalar")
    return vector


def validate_message(document: Any) -> ValidatedMessage:
    if not isinstance(document, dict):
        raise BridgeMessageError("message must be an object")
    if set(document) - {"schemaVersion", "sequence", "kind", "payload"}:
        raise BridgeMessageError("message contains unknown top-level fields")
    if document.get("schemaVersion") != "1.0":
        raise BridgeMessageError("unsupported spool schema")
    sequence = document.get("sequence")
    if not isinstance(sequence, int) or sequence < 1:
        raise BridgeMessageError("sequence must be a positive integer")
    kind = document.get("kind")
    if kind not in {"proxy.upsert", "proxy.delete", "selection.focus", "world.reset"}:
        raise BridgeMessageError("operation is not allowlisted")
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise BridgeMessageError("payload must be an object")
    forbidden = {"python", "script", "command", "shell", "url", "filepath"}
    if forbidden.intersection(key.lower() for key in payload):
        raise BridgeMessageError("executable or external-reference field rejected")
    return ValidatedMessage(sequence=sequence, kind=kind, payload=payload)


def _world_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _find_entity(entity_id: str) -> bpy.types.Object | None:
    for obj in bpy.data.objects:
        if obj.get(ID_PROPERTY) == entity_id:
            return obj
    return None


def _ensure_proxy(payload: dict[str, Any]) -> bpy.types.Object:
    entity_id = payload.get("entityId")
    if not isinstance(entity_id, str) or not entity_id or len(entity_id) > 200:
        raise BridgeMessageError("invalid entityId")
    obj = _find_entity(entity_id)
    if obj is None:
        primitive = payload.get("primitive", "cube")
        if primitive == "cube":
            mesh = bpy.data.meshes.new(f"OpenCraftProxy_{entity_id}")
            obj = bpy.data.objects.new(payload.get("name", "OpenCraft Proxy")[:100], mesh)
            _world_collection().objects.link(obj)
            # Eight vertices and six quad faces avoid context-sensitive bpy.ops calls.
            vertices = [(-.5,-.5,-.5),(.5,-.5,-.5),(.5,.5,-.5),(-.5,.5,-.5),(-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5)]
            faces = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(4,0,3,7)]
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
        else:
            raise BridgeMessageError("unsupported proxy primitive")
        obj[ID_PROPERTY] = entity_id
    return obj


def apply_message(message: ValidatedMessage) -> None:
    payload = message.payload
    if message.kind == "proxy.upsert":
        obj = _ensure_proxy(payload)
        if "location" in payload:
            obj.location = _finite_vector(payload["location"], size=3, name="location")
        if "rotation" in payload:
            obj.rotation_euler = _finite_vector(payload["rotation"], size=3, name="rotation")
        if "scale" in payload:
            scale = _finite_vector(payload["scale"], size=3, name="scale")
            if any(component <= 0 or component > 10_000 for component in scale):
                raise BridgeMessageError("scale is outside the supported range")
            obj.scale = scale
        revision = payload.get("revision", 0)
        if not isinstance(revision, int) or revision < 0:
            raise BridgeMessageError("invalid revision")
        obj[REVISION_PROPERTY] = revision
        obj.name = str(payload.get("name", obj.name))[:100]
    elif message.kind == "proxy.delete":
        entity_id = payload.get("entityId")
        obj = _find_entity(entity_id) if isinstance(entity_id, str) else None
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
    elif message.kind == "selection.focus":
        entity_id = payload.get("entityId")
        obj = _find_entity(entity_id) if isinstance(entity_id, str) else None
        if obj is not None:
            for candidate in bpy.context.selected_objects:
                candidate.select_set(False)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
    elif message.kind == "world.reset":
        for obj in list(bpy.data.objects):
            if obj.get(ID_PROPERTY):
                bpy.data.objects.remove(obj, do_unlink=True)
