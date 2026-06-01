import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { captureEvent } from "../src/index.js";

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
    traceId: "00000000-0000-4000-8000-000000000001",
    spanId: "00000000-0000-4000-8000-000000000002",
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
      assert.equal(call.body.events[0].trace_id, "00000000-0000-4000-8000-000000000001");
      assert.equal(call.body.events[0].span_id, "00000000-0000-4000-8000-000000000002");
      assert.equal(call.body.events[0].payload.token, "[REDACTED]");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("capture spools current event when sidecar ingest is unavailable", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("sidecar unavailable");
  };

  try {
    const workspaceDir = await tempWorkspace();
    const result = await captureEvent({
      eventType: "message_received",
      payload: { content: "hello" },
      trust: "untrusted",
      taint: ["message"],
      hookContext: hookContext(workspaceDir),
    });

    assert.equal(result.captured, true);
    assert.equal(result.forwarded, false);
    assert.equal(result.spooled, true);

    const spoolDir = path.join(workspaceDir, ".autoskill", "spool");
    const files = await fs.readdir(spoolDir);
    assert.equal(files.length, 1);
    const lines = (await fs.readFile(path.join(spoolDir, files[0]), "utf8"))
      .trim()
      .split("\n");
    assert.equal(lines.length, 1);
    assert.equal(JSON.parse(lines[0]).event_type, "message_received");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("capture does not re-spool current event when old spool replay fails", async () => {
  const originalFetch = globalThis.fetch;
  const workspaceDir = await tempWorkspace();
  const spoolDir = path.join(workspaceDir, ".autoskill", "spool");
  await fs.mkdir(spoolDir, { recursive: true });
  await fs.writeFile(
    path.join(spoolDir, "2026-01-01.jsonl"),
    `${JSON.stringify({
      event_id: "old",
      schema_version: 1,
      workspace_id: "workspace-1",
      event_type: "tool_call_end",
      occurred_at: new Date().toISOString(),
      source: "openclaw-plugin",
      trust: "trusted",
      taint: [],
      redaction_state: "redacted",
      payload_hash: "old",
      payload: { id: "old" },
    })}\n`,
  );

  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) {
      return Response.json({ accepted: 1, duplicate: 0, rejected: 0 });
    }
    throw new Error("replay failed");
  };

  try {
    const result = await captureEvent({
      eventType: "tool_call_end",
      payload: { id: "current" },
      trust: "trusted",
      taint: ["tool"],
      hookContext: hookContext(workspaceDir),
    });

    assert.equal(result.forwarded, true);
    assert.equal(result.spooled, undefined);
    assert.equal(result.replay.failed, 1);

    const files = await fs.readdir(spoolDir);
    assert.deepEqual(files, ["2026-01-01.jsonl"]);
    const lines = (await fs.readFile(path.join(spoolDir, files[0]), "utf8"))
      .trim()
      .split("\n");
    assert.equal(lines.length, 1);
    assert.equal(JSON.parse(lines[0]).event_id, "old");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("concurrent capture appends all failed events to the spool", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("sidecar unavailable");
  };

  try {
    const workspaceDir = await tempWorkspace();
    const results = await Promise.all(
      Array.from({ length: 10 }, (_, index) =>
        captureEvent({
          eventType: "tool_call_end",
          payload: { id: `event-${index}` },
          trust: "trusted",
          taint: ["tool"],
          hookContext: hookContext(workspaceDir),
        }),
      ),
    );

    assert.equal(results.every((result) => result.spooled === true), true);

    const spoolDir = path.join(workspaceDir, ".autoskill", "spool");
    const files = await fs.readdir(spoolDir);
    assert.equal(files.length, 1);
    const lines = (await fs.readFile(path.join(spoolDir, files[0]), "utf8"))
      .trim()
      .split("\n");
    assert.equal(lines.length, 10);
    assert.equal(new Set(lines.map((line) => JSON.parse(line).event_id)).size, 10);
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

test("plugin diagnostics reports spool and sidecar status", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, request) => {
    assert.equal(url, "http://127.0.0.1:8765/v1/status");
    assert.equal(request.method, "GET");
    assert.equal(request.headers.authorization, "Bearer token-1");
    return Response.json({
      mode: "autonomous_guarded",
      database_configured: true,
      ingest_auth_configured: true,
      control_auth_configured: false,
      runtime_context_broker: {},
      jobs: { queued: 1 },
    });
  };

  try {
    const workspaceDir = await tempWorkspace();
    const { getPluginDiagnostics } = await import("../src/index.js");
    const result = await getPluginDiagnostics(hookContext(workspaceDir));
    assert.equal(result.enabled, true);
    assert.equal(result.spool.files, 0);
    assert.equal(result.sidecar.reachable, true);
    assert.equal(result.sidecar.status.jobs.queued, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("plugin runtime registers typed OpenClaw hooks", async () => {
  const { default: plugin } = await import("../src/index.js");
  const registrations = [];
  const api = {
    on(hookName, handler, options) {
      registrations.push({ hookName, handler, options });
    },
  };

  plugin.register(api);

  assert.equal(plugin.id, "autoskill");
  assert.deepEqual(
    registrations.map((entry) => entry.hookName).sort(),
    [
      "after_tool_call",
      "before_prompt_build",
      "before_tool_call",
      "gateway_start",
      "llm_input",
      "llm_output",
      "message_received",
      "message_sent",
      "model_call_ended",
      "model_call_started",
      "tool_result_persist",
    ].sort(),
  );
  assert.equal(
    registrations.find((entry) => entry.hookName === "before_prompt_build").options.name,
    "autoskill-context-hint",
  );
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
