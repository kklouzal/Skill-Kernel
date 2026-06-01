import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const captureHooks = [
  ["after-tool-call", "tool_call_end"],
  ["before-tool-call", "tool_call_start"],
  ["gateway-startup", "gateway_startup"],
  ["llm-input", "llm_input"],
  ["llm-output", "llm_output"],
  ["message-received", "message_received"],
  ["message-sent", "message_sent"],
  ["model-call-ended", "model_call_ended"],
  ["model-call-started", "model_call_started"],
];

async function tempWorkspace() {
  return fs.mkdtemp(path.join(os.tmpdir(), "autoskill-hooks-"));
}

function hookContext(workspaceDir) {
  return {
    workspaceDir,
    agentId: "agent-1",
    sessionId: "session-1",
    turnId: "turn-1",
    openclawVersion: "test-openclaw",
    config: {
      autoskill: {
        enabled: true,
        sidecarUrl: "http://127.0.0.1:8765",
        workspaceId: "workspace-1",
        ingestToken: "token-1",
        maxSpoolBytes: 1024 * 1024,
        runtimeContextBroker: {
          enabled: true,
          timeoutMs: 150,
          maxTokens: 100,
        },
      },
    },
  };
}

test("capture hook handlers import and forward redacted envelopes", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, request) => {
    calls.push({ url, request, body: JSON.parse(request.body) });
    return Response.json({ accepted: 1, duplicate: 0, rejected: 0 });
  };

  try {
    for (const [hookDir, eventType] of captureHooks) {
      const workspaceDir = await tempWorkspace();
      const { default: handler } = await import(`../hooks/${hookDir}/handler.js`);

      await handler({ token: "secret", safe: hookDir }, hookContext(workspaceDir));

      const call = calls.at(-1);
      assert.equal(call.url, "http://127.0.0.1:8765/v1/ingest/events");
      assert.equal(call.request.headers.authorization, "Bearer token-1");
      assert.equal(call.body.events.length, 1);
      assert.equal(call.body.events[0].event_type, eventType);
      assert.equal(call.body.events[0].workspace_id, "workspace-1");
      assert.equal(call.body.events[0].payload.token, "[REDACTED]");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("before-prompt-build hook imports and returns sidecar context hints", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, request) => {
    assert.equal(url, "http://127.0.0.1:8765/v1/runtime/context-hint");
    assert.equal(request.headers.authorization, "Bearer token-1");
    const body = JSON.parse(request.body);
    assert.equal(body.user_intent, "do the thing");
    return Response.json({ hint: "use autoskill-example", skill_ids: ["skill-1"], metadata: {} });
  };

  try {
    const workspaceDir = await tempWorkspace();
    const { default: handler } = await import("../hooks/before-prompt-build/handler.js");
    const result = await handler({ prompt: "do the thing" }, hookContext(workspaceDir));
    assert.deepEqual(result, { appendContext: "use autoskill-example" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("every hook directory declares OpenClaw event metadata", async () => {
  const hooksRoot = new URL("../hooks/", import.meta.url);
  const entries = await fs.readdir(hooksRoot, { withFileTypes: true });
  for (const entry of entries.filter((item) => item.isDirectory())) {
    const hookMd = await fs.readFile(new URL(`${entry.name}/HOOK.md`, hooksRoot), "utf8");
    assert.match(hookMd, /^metadata: \{"openclaw":\{"events":\[/m);
    assert.match(hookMd, /^description: ".+"/m);
  }
});
