import crypto from "node:crypto";
import { redactPayload } from "./redaction/index.js";

function sha256Json(value) {
  return crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

export function buildEventEnvelope({ eventType, payload, trust, taint = [], ctx = {}, config }) {
  const redactedPayload = redactPayload(payload ?? {});
  return {
    event_id: crypto.randomUUID(),
    schema_version: 1,
    workspace_id: config.workspaceId,
    agent_id: ctx.agentId ?? null,
    session_id: ctx.sessionId ?? null,
    turn_id: ctx.turnId ?? null,
    event_type: eventType,
    occurred_at: new Date().toISOString(),
    source: "openclaw-plugin",
    trust,
    taint,
    redaction_state: "redacted",
    payload_hash: sha256Json(redactedPayload),
    payload: redactedPayload,
    plugin_version: "0.1.0",
    openclaw_version: ctx.openclawVersion ?? null,
  };
}

