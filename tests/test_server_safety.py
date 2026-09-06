"""Regression tests for authority, durable receipts, approval and local isolation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opencraft_server.auth import AuthError, Principal, TokenAuthority
from opencraft_server.database import Database
from opencraft_server.service import CanonicalWorldService, ServiceError
from opencraft_server.workspace import LocalWorkspace


class PersistentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = [1000000]
        self.db = Database(Path(self.temp.name) / "world.sqlite3")
        self.authority = TokenAuthority(b"test" * 8, clock=lambda: self.now[0])
        self.service = CanonicalWorldService(self.db, self.authority, clock=lambda: self.now[0])
        created = self.service.create_world(name="Test", owner_display_name="Owner")
        self.actor = self.service.authenticate(created["sessionToken"])
        self.token = created["sessionToken"]

    def plan(self, entity="tree", revision=0):
        return {"schemaVersion": "1.0", "worldId": self.actor.world_id, "baseRevision": revision,
                "title": "Create a tree", "operations": [{"kind": "entity.create", "entityId": entity,
                "regionId": "park", "payload": {"name": "Tree", "position": [1, 0, 2]}}]}

    def preview(self, plan=None, actor=None, agent="codex", **kwargs):
        return self.service.preview_plan(actor or self.actor, agent_id=agent, document=plan or self.plan(), **kwargs)

    def commit(self, preview, key="request-1", actor=None, agent="codex", consent=None):
        actor = actor or self.actor
        if consent is None:
            consent = self.service.issue_consent(actor, agent_id=agent, preview_hash=preview["previewHash"])
        return self.service.commit_preview(actor, agent_id=agent, preview_hash=preview["previewHash"],
                                           consent_token=consent, idempotency_key=key)

    def builder(self, role="builder"):
        invite = self.service.create_invite(self.actor, role=role, approval_required=False)
        joined = self.service.redeem_invite(invite["inviteToken"], display_name="Guest")
        return self.service.authenticate(joined["sessionToken"]), invite, joined

    def assert_empty(self):
        context = self.service.context(self.actor)
        self.assertEqual(context["revision"], 0)
        self.assertEqual(context["entities"], [])
        self.assertEqual(self.service.events_after(self.actor, 0)["events"], [])

    def test_preview_does_not_modify_world(self):
        self.preview()
        self.assert_empty()

    def test_receipt_survives_service_restart_and_does_not_need_consumed_consent(self):
        preview = self.preview()
        first = self.commit(preview)
        self.service = CanonicalWorldService(Database(self.db.path), self.authority, clock=lambda: self.now[0])
        second = self.commit(preview, consent="no-longer-needed")
        self.assertEqual(first, second)
        self.assertEqual(len(self.service.events_after(self.actor, 0)["events"]), 1)

    def test_preview_is_bound_to_agent(self):
        preview = self.preview()
        with self.assertRaises(ServiceError):
            self.service.issue_consent(self.actor, agent_id="claude", preview_hash=preview["previewHash"])
        self.assert_empty()

    def test_preview_is_bound_to_actor(self):
        preview = self.preview()
        builder, _, _ = self.builder()
        with self.assertRaises(ServiceError):
            self.service.issue_consent(builder, agent_id="codex", preview_hash=preview["previewHash"])
        self.assert_empty()

    def test_preview_is_bound_to_world(self):
        created = self.service.create_world(name="Other", owner_display_name="Other")
        other = self.service.authenticate(created["sessionToken"])
        with self.assertRaises(ServiceError):
            self.preview(actor=other)
        self.assert_empty()

    def test_idempotency_key_cannot_return_another_actors_receipt(self):
        preview = self.preview()
        self.commit(preview)
        builder, _, _ = self.builder()
        with self.assertRaises(ServiceError) as raised:
            self.commit(preview, actor=builder, consent="irrelevant")
        self.assertEqual(raised.exception.status, 409)

    def test_expired_preview(self):
        preview = self.preview()
        self.now[0] += 600
        with self.assertRaises(ServiceError):
            self.commit(preview)
        self.assert_empty()

    def test_expired_consent(self):
        preview = self.preview()
        token = self.service.issue_consent(self.actor, agent_id="codex", preview_hash=preview["previewHash"], ttl_seconds=1)
        self.now[0] += 1
        with self.assertRaises(ServiceError):
            self.commit(preview, consent=token)
        self.assert_empty()

    def test_preview_changed_after_approval_is_rejected(self):
        first, second = self.preview(), self.preview(self.plan("house"))
        consent = self.service.issue_consent(self.actor, agent_id="codex", preview_hash=first["previewHash"])
        self.commit(second)
        with self.assertRaises(ServiceError) as raised:
            self.commit(first, key="stale", consent=consent)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.service.context(self.actor)["revision"], 1)

    def test_consent_cannot_move_between_previews(self):
        first, second = self.preview(), self.preview(self.plan("house"))
        consent = self.service.issue_consent(self.actor, agent_id="codex", preview_hash=first["previewHash"])
        with self.assertRaises(ServiceError):
            self.commit(second, consent=consent)
        self.assert_empty()

    def test_storage_failure_rolls_back_entities_events_and_consumed_consent(self):
        preview = self.preview()
        consent = self.service.issue_consent(self.actor, agent_id="codex", preview_hash=preview["previewHash"])
        with patch.object(self.service, "_event", side_effect=RuntimeError("simulated disk error")):
            with self.assertRaises(RuntimeError):
                self.commit(preview, consent=consent)
        self.assert_empty()
        self.assertEqual(self.commit(preview, consent=consent)["worldRevision"], 1)

    def test_concurrent_same_key_commits_once(self):
        preview = self.preview()
        consent = self.service.issue_consent(self.actor, agent_id="codex", preview_hash=preview["previewHash"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.commit(preview, consent=consent), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.service.context(self.actor)["revision"], 1)

    def test_empty_explicit_region_scope_fails_closed(self):
        with self.assertRaises(ServiceError):
            self.preview(allowed_region_ids=[])
        self.assert_empty()

    def test_region_scope_cannot_relabel_an_existing_entity(self):
        self.commit(self.preview())
        plan = self.plan(revision=1)
        plan["operations"][0].update(kind="entity.delete", regionId="other", payload={})
        with self.assertRaises(ServiceError) as raised:
            self.preview(plan, allowed_region_ids=["other"])
        self.assertEqual(raised.exception.status, 403)

    def test_guest_creator_cannot_modify_another_owners_entity(self):
        self.commit(self.preview())
        guest, _, _ = self.builder(role="guest_creator")
        plan = self.plan(revision=1)
        plan["operations"][0].update(kind="entity.update", payload={"name": "overwrite"})
        with self.assertRaises(ServiceError):
            self.preview(plan, actor=guest)

    def test_revoked_cached_principal_cannot_read_or_commit(self):
        builder, invite, joined = self.builder()
        preview = self.preview(actor=builder)
        consent = self.service.issue_consent(builder, agent_id="codex", preview_hash=preview["previewHash"])
        self.service.revoke_invite(self.actor, invite["inviteId"])
        with self.assertRaises(AuthError):
            self.service.authenticate(joined["sessionToken"])
        with self.assertRaises(ServiceError):
            self.service.context(builder)
        with self.assertRaises(ServiceError):
            self.commit(preview, actor=builder, consent=consent)
        self.assert_empty()

    def test_role_is_read_from_database_not_principal_argument(self):
        viewer, _, _ = self.builder(role="viewer")
        forged = Principal(viewer.principal_id, viewer.display_name, viewer.world_id, "owner")
        with self.assertRaises(ServiceError):
            self.preview(actor=forged)
        self.assert_empty()

    def test_pending_approval_cannot_outlive_revocation(self):
        invite = self.service.create_invite(self.actor, role="builder", approval_required=True)
        pending = self.service.redeem_invite(invite["inviteToken"], display_name="Guest")
        self.service.decide_join_request(self.actor, pending["requestId"], approve=True)
        self.service.revoke_invite(self.actor, invite["inviteId"])
        self.assertEqual(self.service.claim_join_request(pending["requestToken"])["status"], "rejected")

    def test_concurrent_invite_redeem_respects_quota(self):
        invite = self.service.create_invite(self.actor, role="viewer", max_uses=1, approval_required=False)
        def redeem(_):
            try:
                return self.service.redeem_invite(invite["inviteToken"], display_name="Guest")["status"]
            except ServiceError:
                return "rejected"
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(redeem, range(4))).count("joined"), 1)

    def test_unsupported_operations_never_claim_success(self):
        for kind in ("terrain.patch", "semantic.link", "shell.exec"):
            with self.subTest(kind=kind):
                plan = self.plan()
                plan["operations"][0]["kind"] = kind
                with self.assertRaises(ServiceError):
                    self.preview(plan)
        self.assert_empty()

    def test_identity_fields_and_boolean_revisions_are_rejected(self):
        for field in ("id", "entityId", "ownerId", "regionId", "worldId", "revision"):
            plan = self.plan()
            plan["operations"][0]["payload"][field] = "override"
            with self.subTest(field=field), self.assertRaises(ServiceError):
                self.preview(plan)
        plan = self.plan()
        plan["baseRevision"] = False
        with self.assertRaises(ServiceError):
            self.preview(plan)
        self.assert_empty()

    def test_mutating_original_plan_does_not_change_saved_preview(self):
        plan = self.plan()
        preview = self.preview(plan)
        plan["operations"][0]["payload"]["name"] = "changed after preview"
        self.commit(preview)
        self.assertEqual(self.service.context(self.actor)["entities"][0]["payload"]["name"], "Tree")

    def test_context_and_history_redact_nested_credentials(self):
        plan = self.plan()
        plan["operations"][0]["payload"]["settings"] = {"sessionToken": "synthetic-sensitive-value"}
        self.commit(self.preview(plan))
        context = self.service.context(self.actor)
        self.assertEqual(context["entities"][0]["payload"]["settings"]["sessionToken"], "[REDACTED]")
        history = self.service.events_after(self.actor, 0)
        self.assertNotIn("synthetic-sensitive-value", str(history))

    def test_delete_checks_expected_revision(self):
        self.commit(self.preview())
        plan = self.plan(revision=1)
        plan["operations"][0].update(kind="entity.delete", payload={}, expectedRevision=99)
        with self.assertRaises(ServiceError):
            self.preview(plan)

    def test_undo_does_not_clobber_later_changes(self):
        first = self.commit(self.preview())
        self.commit(self.preview(self.plan("house", 1)), key="second")
        with self.assertRaises(ServiceError):
            self.service.undo(self.actor, first["transactionId"])
        self.assertEqual(len(self.service.context(self.actor)["entities"]), 2)

    def test_undo_rejects_wrong_confirmation_revision(self):
        result = self.commit(self.preview())
        with self.assertRaises(ServiceError):
            self.service.undo(self.actor, result["transactionId"], expected_revision=0)
        self.assertEqual(self.service.context(self.actor)["revision"], 1)

    def test_local_initialization_is_atomic_and_repeatable(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            actors = list(pool.map(lambda _: self.service.local_principal(create=True), range(4)))
        self.assertTrue(all(actor == actors[0] for actor in actors))
        self.assertEqual(self.service.local_principal(), actors[0])

    def test_context_is_bounded_and_history_cursor_is_monotonic(self):
        plan = self.plan()
        plan["operations"] = [deepcopy(plan["operations"][0]), deepcopy(plan["operations"][0])]
        plan["operations"][1]["entityId"] = "house"
        self.commit(self.preview(plan))
        snapshot = self.service.context(self.actor, limit=1)
        self.assertTrue(snapshot["truncated"])
        self.assertEqual(len(snapshot["entities"]), 1)
        history = self.service.events_after(self.actor, 0, limit=1)
        self.assertEqual(history["nextCursor"], 1)
        self.assertEqual(self.service.events_after(self.actor, 1)["events"], [])


class LocalWorkspaceTests(unittest.TestCase):
    def test_restart_preserves_world_without_storing_a_provider_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace"
            with self.assertRaises(ServiceError):
                LocalWorkspace(path)
            first = LocalWorkspace(path, create=True)
            second = LocalWorkspace(path)
            self.assertEqual(first.actor, second.actor)
            self.assertFalse((path / "credentials.json").exists())
            self.assertEqual(first.database.integrity_check(), "ok")

    def test_two_workspaces_do_not_share_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            a = LocalWorkspace(Path(directory) / "a", create=True)
            b = LocalWorkspace(Path(directory) / "b", create=True)
            self.assertNotEqual(a.actor.world_id, b.actor.world_id)
