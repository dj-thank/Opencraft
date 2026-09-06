from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolState:
    role: str
    in_world: bool
    has_selection: bool = False
    has_preview: bool = False
    has_committed_transaction: bool = False
    can_share: bool = False


_READ_TOOLS = {
    "opencraft_get_context",
    "opencraft_search_world",
    "opencraft_focus_entity",
    "opencraft_set_waypoint",
}


def published_tools(state: ToolState) -> tuple[str, ...]:
    if not state.in_world:
        return ()
    tools = set(_READ_TOOLS)
    can_build = state.role in {"builder", "moderator", "owner"}
    if can_build and state.has_selection:
        tools.add("opencraft_preview_build")
    if can_build and state.has_preview:
        tools.add("opencraft_request_commit")
    if can_build and state.has_committed_transaction:
        tools.add("opencraft_undo_agent_transaction")
    if state.can_share:
        tools.add("opencraft_share_object_card")
    return tuple(sorted(tools))


def assert_safe_tool_catalog(tools: tuple[str, ...]) -> None:
    forbidden = ("microphone", "raw_audio", "credential", "shell", "python", "javascript", "filesystem")
    for name in tools:
        lowered = name.lower()
        if any(fragment in lowered for fragment in forbidden):
            raise ValueError(f"unsafe WebMCP tool name: {name}")
