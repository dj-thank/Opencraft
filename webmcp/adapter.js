const READ_TOOLS = Object.freeze([
  "opencraft_get_context",
  "opencraft_search_world",
  "opencraft_focus_entity",
  "opencraft_set_waypoint",
]);

export function computeToolNames(state) {
  if (!state?.inWorld) return [];
  const tools = new Set(READ_TOOLS);
  const canBuild = ["builder", "moderator", "owner"].includes(state.role);
  if (canBuild && state.hasSelection) tools.add("opencraft_preview_build");
  if (canBuild && state.hasPreview) tools.add("opencraft_request_commit");
  if (canBuild && state.hasCommittedTransaction) tools.add("opencraft_undo_agent_transaction");
  if (state.canShare) tools.add("opencraft_share_object_card");
  return [...tools].sort();
}

function schema(properties = {}, required = []) {
  return { type: "object", additionalProperties: false, properties, required };
}

export function buildToolDefinitions(state, handlers) {
  const names = computeToolNames(state);
  const definitions = {
    opencraft_get_context: {
      description: "Read a privacy-filtered summary of the visible OpenCraft world context",
      inputSchema: schema({ detail: { enum: ["summary", "selection", "nearby"] } }),
    },
    opencraft_search_world: {
      description: "Search visible world entities without reading private data",
      inputSchema: schema({ query: { type: "string", minLength: 1, maxLength: 300 } }, ["query"]),
    },
    opencraft_focus_entity: {
      description: "Focus an entity already visible to the current user",
      inputSchema: schema({ entityId: { type: "string", minLength: 1, maxLength: 200 } }, ["entityId"]),
    },
    opencraft_set_waypoint: {
      description: "Suggest a waypoint; this never moves the avatar automatically",
      inputSchema: schema({ entityId: { type: "string" }, position: { type: "array", minItems: 3, maxItems: 3 } }),
    },
    opencraft_preview_build: {
      description: "Create a non-mutating ghost preview for a bounded construction request",
      inputSchema: schema({ intent: { type: "string", minLength: 1, maxLength: 2000 } }, ["intent"]),
    },
    opencraft_request_commit: {
      description: "Open human consent UI for the exact current preview; this tool cannot commit directly",
      inputSchema: schema({ previewHash: { type: "string", pattern: "^[a-f0-9]{64}$" } }, ["previewHash"]),
    },
    opencraft_undo_agent_transaction: {
      description: "Request a policy-checked undo of an eligible agent transaction",
      inputSchema: schema({ transactionId: { type: "string", minLength: 1 } }, ["transactionId"]),
    },
    opencraft_share_object_card: {
      description: "Open human confirmation before sharing an object card",
      inputSchema: schema({ entityId: { type: "string", minLength: 1 } }, ["entityId"]),
    },
  };

  return names.map((name) => ({
    name,
    ...definitions[name],
    execute: async (args) => {
      const handler = handlers?.[name];
      if (typeof handler !== "function") throw new Error(`No handler registered for ${name}`);
      return handler(args);
    },
  }));
}

export async function registerOpenCraftTools({ modelContext = document.modelContext, state, handlers, signal }) {
  if (!modelContext?.registerTool) return { supported: false, names: [] };
  const definitions = buildToolDefinitions(state, handlers);
  for (const definition of definitions) await modelContext.registerTool(definition, { signal });
  return { supported: true, names: definitions.map((tool) => tool.name) };
}
