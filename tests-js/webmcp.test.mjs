import test from "node:test";
import assert from "node:assert/strict";
import { buildToolDefinitions, computeToolNames, registerOpenCraftTools } from "../webmcp/adapter.js";

test("viewer never receives build or commit request tools", () => {
  const tools = computeToolNames({ role: "viewer", inWorld: true, hasSelection: true, hasPreview: true });
  assert.equal(tools.includes("opencraft_preview_build"), false);
  assert.equal(tools.includes("opencraft_request_commit"), false);
});

test("commit request appears only after preview", () => {
  const before = computeToolNames({ role: "builder", inWorld: true, hasSelection: true, hasPreview: false });
  const after = computeToolNames({ role: "builder", inWorld: true, hasSelection: true, hasPreview: true });
  assert.equal(before.includes("opencraft_request_commit"), false);
  assert.equal(after.includes("opencraft_request_commit"), true);
});

test("tool definitions contain no direct microphone or code execution surface", () => {
  const state = { role: "owner", inWorld: true, hasSelection: true, hasPreview: true, hasCommittedTransaction: true, canShare: true };
  const handlers = Object.fromEntries(computeToolNames(state).map((name) => [name, async () => ({ ok: true })]));
  const serialized = JSON.stringify(buildToolDefinitions(state, handlers)).toLowerCase();
  for (const forbidden of ["raw_audio", "credential", "shell.exec", "python.exec", "javascript.exec", "filesystem"]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("unsupported browsers degrade without throwing", async () => {
  const result = await registerOpenCraftTools({ modelContext: null, state: { inWorld: true }, handlers: {} });
  assert.deepEqual(result, { supported: false, names: [] });
});
