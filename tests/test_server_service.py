from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from opencraft_server.auth import AuthError, TokenAuthority
from opencraft_server.database import Database
from opencraft_server.service import CanonicalWorldService, ServiceError


class ServerServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name)
        self.database = Database(path / "world.sqlite3")
        self.authority = TokenAuthority(b"s" * 32, clock=lambda: 1_000_000)
        self.service = CanonicalWorldService(self.database, self.authority, clock=lambda: 1_000_000)
        created = self.service.create_world(name="碧島", owner_display_name="Owner")
        self.owner_token = created["sessionToken"]
        self.owner = self.service.authenticate(self.owner_token)

    def tearDown(self):
        self.directory.cleanup()

    def plan(self, *, revision=0, entity_id="lighthouse"):
        return {
            "schemaVersion": "1.0",
            "planId": "plan-1",
            "worldId": self.owner.world_id,
            "baseRevision": revision,
            "title": "灯台を建てる",
            "assumptions": ["既存の道を残す"],
            "costUnits": 20,
            "operations": [
                {
                    "kind": "entity.create",
                    "regionId": "harbor",
                    "entityId": entity_id,
                    "payload": {"name": "灯台", "position": [1, 2, 3]},
                }
            ],
        }

    def test_immediate_invite_issues_revocable_session(self):
        invite = self.service.create_invite(self.owner, role="builder", approval_required=False)
        joined = self.service.redeem_invite(invite["inviteToken"], display_name="Builder")
        self.assertEqual(joined["status"], "joined")
        builder = self.service.authenticate(joined["sessionToken"])
        self.assertEqual(builder.role, "builder")
        self.service.revoke_invite(self.owner, invite["inviteId"])
        with self.assertRaises(AuthError):
            self.service.authenticate(joined["sessionToken"])

    def test_approval_request_is_single_claim(self):
        invite = self.service.create_invite(self.owner, role="builder", approval_required=True)
        pending = self.service.redeem_invite(invite["inviteToken"], display_name="Builder")
        self.assertEqual(self.service.claim_join_request(pending["requestToken"])["status"], "pending")
        self.service.decide_join_request(self.owner, pending["requestId"], approve=True)
        joined = self.service.claim_join_request(pending["requestToken"])
        self.assertEqual(joined["status"], "joined")
        with self.assertRaises(ServiceError):
            self.service.claim_join_request(pending["requestToken"])

    def test_commit_is_preview_bound_idempotent_and_undoable(self):
        preview = self.service.preview_plan(
            self.owner, agent_id="agent-1", document=self.plan(), allowed_region_ids=["harbor"]
        )
        token = self.service.issue_consent(
            self.owner, agent_id="agent-1", preview_hash=preview["previewHash"]
        )
        result = self.service.commit_preview(
            self.owner,
            agent_id="agent-1",
            preview_hash=preview["previewHash"],
            consent_token=token,
            idempotency_key="request-1",
        )
        retried = self.service.commit_preview(
            self.owner,
            agent_id="agent-1",
            preview_hash=preview["previewHash"],
            consent_token="already-consumed-is-not-needed-for-idempotent-retry",
            idempotency_key="request-1",
        )
        self.assertEqual(result, retried)
        context = self.service.context(self.owner)
        self.assertEqual(context["entities"][0]["entityId"], "lighthouse")
        undone = self.service.undo(self.owner, result["transactionId"])
        self.assertEqual(undone["undoes"], result["transactionId"])
        self.assertEqual(self.service.context(self.owner)["entities"], [])

    def test_same_idempotency_key_for_different_preview_is_rejected(self):
        preview = self.service.preview_plan(self.owner, agent_id="agent-1", document=self.plan())
        token = self.service.issue_consent(self.owner, agent_id="agent-1", preview_hash=preview["previewHash"])
        self.service.commit_preview(self.owner, agent_id="agent-1", preview_hash=preview["previewHash"], consent_token=token, idempotency_key="same")
        second = self.service.preview_plan(self.owner, agent_id="agent-1", document=self.plan(revision=1, entity_id="tree"))
        second_token = self.service.issue_consent(self.owner, agent_id="agent-1", preview_hash=second["previewHash"])
        with self.assertRaises(ServiceError) as raised:
            self.service.commit_preview(self.owner, agent_id="agent-1", preview_hash=second["previewHash"], consent_token=second_token, idempotency_key="same")
        self.assertEqual(raised.exception.status, 409)

    def test_viewer_cannot_preview(self):
        invite = self.service.create_invite(self.owner, role="viewer", approval_required=False)
        joined = self.service.redeem_invite(invite["inviteToken"], display_name="Viewer")
        viewer = self.service.authenticate(joined["sessionToken"])
        document = self.plan()
        with self.assertRaises(ServiceError) as raised:
            self.service.preview_plan(viewer, agent_id="agent", document=document)
        self.assertEqual(raised.exception.status, 403)

    def test_database_integrity(self):
        self.assertEqual(self.database.integrity_check(), "ok")


if __name__ == "__main__":
    unittest.main()
