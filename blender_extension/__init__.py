from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup

from .bridge import BridgeMessageError, apply_message, validate_message

bl_info = {
    "name": "OpenCraft World Bridge",
    "author": "OpenCraft contributors",
    "version": (0, 16, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > OpenCraft",
    "description": "Apply validated OpenCraft world operations through a local spool",
    "category": "3D View",
}

_TIMER_INTERVAL_SECONDS = 0.1
_LAST_SEQUENCE = 0
_REGISTERED = False


def _preferences() -> "OpenCraftPreferences | None":
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def _spool_directory() -> Path | None:
    preferences = _preferences()
    if preferences is None or not preferences.spool_directory:
        return None
    return Path(bpy.path.abspath(preferences.spool_directory)).expanduser().resolve()


def _write_ack(directory: Path, payload: dict[str, Any]) -> None:
    ack_dir = directory / "outbox"
    ack_dir.mkdir(parents=True, exist_ok=True)
    temp = ack_dir / ".ack.tmp"
    final = ack_dir / "ack.json"
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(final)


def _consume_one(path: Path, directory: Path) -> None:
    global _LAST_SEQUENCE
    try:
        if path.stat().st_size > 1_000_000:
            raise BridgeMessageError("spool message exceeds 1 MiB")
        document = json.loads(path.read_text(encoding="utf-8"))
        message = validate_message(document)
        if message.sequence <= _LAST_SEQUENCE:
            raise BridgeMessageError("message sequence is stale or replayed")
        apply_message(message)
        _LAST_SEQUENCE = message.sequence
        _write_ack(directory, {"schemaVersion": "1.0", "sequence": message.sequence, "status": "applied"})
    except (OSError, json.JSONDecodeError, BridgeMessageError, RuntimeError) as exc:
        _write_ack(directory, {"schemaVersion": "1.0", "status": "rejected", "error": type(exc).__name__})
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def poll_spool() -> float | None:
    if not _REGISTERED:
        return None
    directory = _spool_directory()
    if directory is None:
        return _TIMER_INTERVAL_SECONDS
    inbox = directory / "inbox"
    try:
        inbox.mkdir(parents=True, exist_ok=True)
        candidates = sorted(inbox.glob("*.json"), key=lambda path: path.name)
        if candidates:
            _consume_one(candidates[0], directory)
    except OSError:
        pass
    return _TIMER_INTERVAL_SECONDS


@persistent
def reset_after_load(_unused: object) -> None:
    global _LAST_SEQUENCE
    _LAST_SEQUENCE = 0


class OpenCraftPreferences(AddonPreferences):
    bl_idname = __package__

    spool_directory: StringProperty(
        name="Local spool directory",
        subtype="DIR_PATH",
        description="Directory shared only with the local OpenCraft sidecar",
    )

    def draw(self, _context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "spool_directory")
        layout.label(text="The extension never accepts executable Python from a world")


class OpenCraftSceneState(PropertyGroup):
    connected: BoolProperty(name="Sidecar available", default=False)


class OPENCRAFT_OT_check_sidecar(Operator):
    bl_idname = "opencraft.check_sidecar"
    bl_label = "Check local bridge"
    bl_description = "Check whether the configured local spool exists"

    def execute(self, context: bpy.types.Context) -> set[str]:
        directory = _spool_directory()
        available = bool(directory and directory.exists())
        context.scene.opencraft_state.connected = available
        self.report({"INFO"} if available else {"WARNING"}, "Local bridge is available" if available else "Configure or start the local sidecar")
        return {"FINISHED"}


class OPENCRAFT_PT_world_bridge(Panel):
    bl_label = "OpenCraft"
    bl_idname = "OPENCRAFT_PT_world_bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenCraft"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = context.scene.opencraft_state
        row = layout.row()
        row.label(text="Local bridge", icon="CHECKMARK" if state.connected else "UNLINKED")
        layout.operator(OPENCRAFT_OT_check_sidecar.bl_idname)
        layout.separator()
        layout.label(text="World changes require server authorization")
        layout.label(text="No arbitrary scripts are executed")


_CLASSES = (
    OpenCraftPreferences,
    OpenCraftSceneState,
    OPENCRAFT_OT_check_sidecar,
    OPENCRAFT_PT_world_bridge,
)


def register() -> None:
    global _REGISTERED
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.opencraft_state = bpy.props.PointerProperty(type=OpenCraftSceneState)
    if reset_after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reset_after_load)
    _REGISTERED = True
    if not bpy.app.timers.is_registered(poll_spool):
        bpy.app.timers.register(poll_spool, first_interval=_TIMER_INTERVAL_SECONDS, persistent=True)


def unregister() -> None:
    global _REGISTERED
    _REGISTERED = False
    if bpy.app.timers.is_registered(poll_spool):
        bpy.app.timers.unregister(poll_spool)
    if reset_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(reset_after_load)
    if hasattr(bpy.types.Scene, "opencraft_state"):
        del bpy.types.Scene.opencraft_state
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
