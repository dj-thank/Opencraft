"""OpenCraft canonical domain foundation.

Deployment, Blender, MCP, WebMCP, browser, and model-provider integrations are adapters around these invariants.
"""

from .agent import AgentPlan, CapabilityGrant, PlanValidationError, validate_agent_plan
from .chunking import ChunkCoord, chunk_for_position
from .consent import ConsentError, ConsentStore
from .world import ConflictError, PermissionDenied, WorldStore

__all__ = [
    "AgentPlan",
    "CapabilityGrant",
    "ChunkCoord",
    "ConflictError",
    "ConsentError",
    "ConsentStore",
    "PermissionDenied",
    "PlanValidationError",
    "WorldStore",
    "chunk_for_position",
    "validate_agent_plan",
]
