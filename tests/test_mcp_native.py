"""Real SDK/protocol and subprocess tests, NOT logged-in native LLM tests.

Required dependency: pip install -e '.[dev]'. Missing SDK is a test failure,
not a skip that could incorrectly turn the release gate green.
"""
import asyncio
from pathlib import Path
import tempfile
import sys
import unittest

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import ElicitResult, InputRequiredResult

from opencraft_server.mcp import create_server
from opencraft_server.workspace import LocalWorkspace

ROOT = Path(__file__).resolve().parents[1]


class NativeMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = LocalWorkspace(Path(self.temp.name) / "workspace", create=True)

    def plan(self, workspace=None):
        workspace = workspace or self.workspace
        return {"schemaVersion": "1.0", "worldId": workspace.actor.world_id, "baseRevision": 0,
                "title": "灯台を建てる", "operations": [{"kind": "entity.create", "entityId": "lighthouse",
                "regionId": "harbor", "payload": {"name": "灯台", "position": [1, 0, 3]}}]}

    async def call(self, client, name, arguments=None):
        result = await asyncio.wait_for(client.call_tool(name, arguments or {}), timeout=15)
        self.assertFalse(result.is_error, str(result.content))
        self.assertIsNotNone(result.structured_content)
        return result.structured_content

    async def approve(self, context, params):
        self.assertIn("UNTRUSTED DATA", params.message)
        return ElicitResult(action="accept", content={"approve": True})

    async def rejected(self, client, arguments):
        try:
            result = await asyncio.wait_for(client.call_tool("opencraft_request_commit", arguments), timeout=15)
            self.assertTrue(result.is_error or result.structured_content.get("status") == "not-committed")
        except MCPError as exc:
            self.assertNotEqual(exc.code, -32001, "a timeout is not an authorization rejection")
        self.assertEqual(self.workspace.context()["revision"], 0)
        self.assertEqual(self.workspace.context()["entities"], [])

    async def test_read_only_publication_and_no_approval_argument(self):
        async with Client(create_server(self.workspace, read_only=True)) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            self.assertEqual(names, {"opencraft_get_context", "opencraft_get_history"})
        async with Client(create_server(self.workspace)) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(len(tools), 6)
            self.assertNotIn("confirmation", tools["opencraft_request_commit"].input_schema["properties"])
            self.assertNotIn("consent_token", str(tools["opencraft_request_commit"].input_schema))
            self.assertTrue(all(not any(x in name for x in ("shell", "exec", "credential", "voice")) for name in tools))

    async def test_each_native_profile_commits_retries_and_undoes_in_both_protocol_eras(self):
        for name in ("codex", "claude"):
            for mode in ("auto", "legacy"):
                with self.subTest(client=name, mode=mode):
                    workspace = LocalWorkspace(Path(self.temp.name) / f"{name}-{mode}", create=True)
                    confirmations = []
                    async def accept(context, params):
                        confirmations.append(params.message)
                        return await self.approve(context, params)
                    server = create_server(workspace, client_name=name)
                    async with Client(server, mode=mode, elicitation_callback=accept) as client:
                        preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan(workspace)})
                        self.assertEqual(workspace.context()["revision"], 0)
                        args = {"preview_hash": preview["previewHash"], "request_id": "one-operation"}
                        first = await self.call(client, "opencraft_request_commit", args)
                        second = await self.call(client, "opencraft_request_commit", args)
                        self.assertEqual(first, second)
                        self.assertEqual(len(confirmations), 1)
                        self.assertIn(preview["previewHash"], confirmations[0])
                        self.assertEqual(workspace.context()["revision"], 1)
                        undo = await self.call(client, "opencraft_undo_agent_transaction", {"transaction_id": first["transactionId"], "expected_revision": 1})
                        self.assertEqual(undo["undoes"], first["transactionId"])
                        self.assertEqual(workspace.context()["entities"], [])
                        self.assertEqual(len(confirmations), 2)

    async def test_decline_cancel_and_unchecked_approval_do_not_commit(self):
        for mode in ("auto", "legacy"):
            for action in ("decline", "cancel", "accept"):
                with self.subTest(mode=mode, action=action):
                    async def reject(context, params):
                        return ElicitResult(action=action, content={"approve": False} if action == "accept" else None)
                    async with Client(create_server(self.workspace), mode=mode, elicitation_callback=reject) as client:
                        preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan()})
                        await self.rejected(client, {"preview_hash": preview["previewHash"], "request_id": f"{mode}-{action}"})

    async def test_missing_elicitation_support_fails_closed(self):
        for mode in ("auto", "legacy"):
            async with Client(create_server(self.workspace), mode=mode) as client:
                preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan()})
                await self.rejected(client, {"preview_hash": preview["previewHash"], "request_id": "no-forms"})

    async def test_model_supplied_confirmation_cannot_bypass_human(self):
        async def reject(context, params):
            return ElicitResult(action="decline")
        async with Client(create_server(self.workspace), elicitation_callback=reject) as client:
            preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan()})
            await self.rejected(client, {"preview_hash": preview["previewHash"], "request_id": "injected",
                                         "confirmation": {"approve": True}})

    async def test_preview_is_revalidated_after_the_user_answers(self):
        async def intervening_change(context, params):
            other = self.plan()
            other["operations"][0]["entityId"] = "another-build"
            service, actor = self.workspace.service, self.workspace.actor
            preview = service.preview_plan(actor, agent_id="other", document=other)
            token = service.issue_consent(actor, agent_id="other", preview_hash=preview["previewHash"])
            service.commit_preview(actor, agent_id="other", preview_hash=preview["previewHash"], consent_token=token, idempotency_key="intervening")
            return ElicitResult(action="accept", content={"approve": True})
        async with Client(create_server(self.workspace), elicitation_callback=intervening_change) as client:
            preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan()})
            result = await client.call_tool("opencraft_request_commit", {"preview_hash": preview["previewHash"], "request_id": "stale"})
            self.assertTrue(result.is_error)
            self.assertEqual([e["entityId"] for e in self.workspace.context()["entities"]], ["another-build"])

    async def test_request_state_is_integrity_protected(self):
        async with Client(create_server(self.workspace)) as client:
            preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan()})
            args = {"preview_hash": preview["previewHash"], "request_id": "tamper"}
            first = await client.session.call_tool("opencraft_request_commit", args, allow_input_required=True)
            self.assertIsInstance(first, InputRequiredResult)
            answers = {key: ElicitResult(action="accept", content={"approve": True}) for key in first.input_requests}
            with self.assertRaises(MCPError) as error:
                await client.session.call_tool("opencraft_request_commit", args, input_responses=answers,
                                               request_state=first.request_state + "changed", allow_input_required=True)
            self.assertEqual(error.exception.code, -32602)
            self.assertEqual(self.workspace.context()["revision"], 0)

    async def test_stdio_round_trip_and_restart_each_client_without_provider_keys(self):
        for name in ("codex", "claude"):
            for mode in ("auto", "legacy"):
                with self.subTest(client=name, mode=mode):
                    path = Path(self.temp.name) / f"stdio-{name}-{mode}"
                    workspace = LocalWorkspace(path, create=True)
                    params = StdioServerParameters(command=sys.executable,
                        args=["-m", "opencraft_server.mcp", "--data-dir", str(path), "--client", name],
                        env={"PYTHONPATH": str(ROOT / "src")})
                    async with Client(params, mode=mode, elicitation_callback=self.approve) as client:
                        preview = await self.call(client, "opencraft_preview_build", {"plan": self.plan(workspace)})
                        args = {"preview_hash": preview["previewHash"], "request_id": "survive-restart"}
                        receipt = await self.call(client, "opencraft_request_commit", args)
                    async with Client(params, mode=mode) as restarted:
                        snapshot = await self.call(restarted, "opencraft_get_context")
                        self.assertEqual(snapshot["revision"], 1)
                        self.assertEqual(snapshot["entities"][0]["entityId"], "lighthouse")
                        self.assertEqual(await self.call(restarted, "opencraft_request_commit", args), receipt)
