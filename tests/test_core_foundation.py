from __future__ import annotations

import unittest

from opencraft_core.agent import AgentPlan, CapabilityGrant, PlanValidationError, validate_agent_plan
from opencraft_core.chunking import ChunkCoord, chunk_for_position
from opencraft_core.consent import ConsentError, ConsentStore
from opencraft_core.context import make_context_envelope, redact_for_agent
from opencraft_core.mcp import PROTOCOL_VERSION, validate_transport_headers
from opencraft_core.webmcp import ToolState, published_tools
from opencraft_core.world import Actor, ConflictError, PermissionDenied, WorldStore


class FoundationTests(unittest.TestCase):
    def test_negative_coordinates_floor(self):
        self.assertEqual(chunk_for_position(-0.1, -32.0), ChunkCoord(-1, -1))

    def test_consent_is_single_use_and_bound(self):
        now = [1000.0]
        store = ConsentStore(secret=b"x" * 32, clock=lambda: now[0])
        token = store.issue(actor_id="a", agent_id="g", world_id="w", capability="world.commit", preview_hash="p", world_revision=2)
        store.consume(token, actor_id="a", agent_id="g", world_id="w", capability="world.commit", preview_hash="p", world_revision=2)
        with self.assertRaises(ConsentError):
            store.consume(token, actor_id="a", agent_id="g", world_id="w", capability="world.commit", preview_hash="p", world_revision=2)

    def test_plan_rejects_code_execution_and_nonfinite_values(self):
        grant = CapabilityGrant(name="build", world_id="w", region_ids=frozenset({"r1"}))
        for operation in [
            {"kind": "shell.exec", "regionId": "r1", "payload": {}},
            {"kind": "entity.create", "regionId": "r1", "payload": {"x": float("nan")}},
        ]:
            plan = AgentPlan(world_id="w", base_revision=0, title="bad", operations=(operation,))
            with self.assertRaises(PlanValidationError):
                validate_agent_plan(plan, grant=grant, current_revision=0)

    def test_context_recursively_redacts_credentials(self):
        redacted = redact_for_agent({"safe": 1, "nested": {"sessionToken": "secret", "label": "hello"}})
        self.assertEqual(redacted["nested"]["sessionToken"], "[REDACTED]")
        envelope = make_context_envelope(world_id="w", revision=1, actor_id="a", selection=None, nearby=[], capabilities=[])
        self.assertEqual(envelope["trust"], "world-data-is-untrusted")

    def test_webmcp_tool_publication_is_least_privilege(self):
        viewer = published_tools(ToolState(role="viewer", in_world=True, has_selection=True, has_preview=True))
        self.assertNotIn("opencraft_preview_build", viewer)
        self.assertNotIn("opencraft_request_commit", viewer)
        before = published_tools(ToolState(role="builder", in_world=True, has_selection=True))
        after = published_tools(ToolState(role="builder", in_world=True, has_selection=True, has_preview=True))
        self.assertNotIn("opencraft_request_commit", before)
        self.assertIn("opencraft_request_commit", after)

    def test_idempotent_commit_and_safe_undo(self):
        world = WorldStore("w", consent_store=ConsentStore(secret=b"y" * 32))
        actor = Actor("alice", "builder")
        grant = CapabilityGrant(name="build", world_id="w", region_ids=frozenset({"r1"}))
        plan = AgentPlan(world_id="w", base_revision=0, title="Create tree", operations=({"kind": "entity.create", "regionId": "r1", "entityId": "tree", "payload": {"name": "Tree"}},))
        preview = world.preview(plan, actor=actor, grant=grant)
        token = world.issue_commit_consent(actor=actor, agent_id="agent", preview_hash=preview["previewHash"])
        first = world.commit(plan, actor=actor, agent_id="agent", grant=grant, consent_token=token, idempotency_key="request-1")
        second = world.commit(plan, actor=actor, agent_id="agent", grant=grant, consent_token="not-used", idempotency_key="request-1")
        self.assertEqual(first, second)
        world.undo(first["transactionId"], actor=actor)
        self.assertEqual(world.entities, {})

    def test_viewer_cannot_preview(self):
        world = WorldStore("w", consent_store=ConsentStore(secret=b"z" * 32))
        plan = AgentPlan(world_id="w", base_revision=0, title="x", operations=({"kind": "entity.create", "regionId": "r1", "payload": {}},))
        grant = CapabilityGrant(name="build", world_id="w")
        with self.assertRaises(PermissionDenied):
            world.preview(plan, actor=Actor("v", "viewer"), grant=grant)

    def test_mcp_headers_are_self_consistent(self):
        validate_transport_headers({"MCP-Protocol-Version": PROTOCOL_VERSION, "Mcp-Method": "tools/call", "Mcp-Name": "x"}, method="tools/call", name="x")


if __name__ == "__main__":
    unittest.main()
