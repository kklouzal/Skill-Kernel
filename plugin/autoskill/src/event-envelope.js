import crypto from "node:crypto";
import { redactPayload } from "./redaction/index.js";

function sha256Json(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
}

export function buildEventEnvelope({ eventType, payload, trust, taint = [], ctx = {}, config }) {
  const redactedPayload = redactPayload(payload ?? {}, {
    captureRawConversation: config.captureRawConversation === true,
  });
  const eventId = crypto.randomUUID();
  const traceId = ctx.traceId ?? crypto.randomUUID();
  const spanId = ctx.spanId ?? crypto.randomUUID();
  const sourceEventKey =
    ctx.sourceEventKey ??
    payload?.source_event_key ??
    payload?.sourceEventKey ??
    payload?.event_id ??
    payload?.eventId ??
    payload?.id ??
    eventId;
  return {
    event_id: eventId,
    schema_version: 1,
    workspace_id: config.workspaceId,
    trace_id: traceId,
    span_id: spanId,
    parent_span_id: ctx.parentSpanId ?? null,
    agent_id: ctx.agentId ?? null,
    session_id: ctx.sessionId ?? null,
    turn_id: ctx.turnId ?? null,
    event_type: eventType,
    occurred_at: new Date().toISOString(),
    source: "openclaw-plugin",
    source_event_key: String(sourceEventKey),
    trust,
    taint,
    redaction_state: "redacted",
    evidence_fidelity: evidenceFidelityForEvent(eventType, payload),
    raw_evidence_record_id: null,
    payload_hash: sha256Json(redactedPayload),
    payload: redactedPayload,
    plugin_version: "0.1.0",
    openclaw_version: ctx.openclawVersion ?? null,
  };
}

function evidenceFidelityForEvent(eventType, payload) {
  if (payload?.evidence_fidelity) {
    return payload.evidence_fidelity;
  }
  if (
    [
      "gateway_startup",
      "model_call_started",
      "model_call_ended",
      "tool_result_persist",
    ].includes(eventType)
  ) {
    return "metadata_only";
  }
  return "redacted_derivative";
}
