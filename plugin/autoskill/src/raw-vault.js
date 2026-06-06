import crypto from "node:crypto";

import { redactPayload } from "./redaction/index.js";

export function buildRawEvidenceRecord({ eventType, payload, taint = [], ctx = {}, config, envelope }) {
  const rawPayload = redactPayload(payload ?? {}, { captureRawConversation: true });
  const encryptedPayload = encryptJson(
    {
      schema_version: "autoskill.plugin-raw-evidence-payload.v1",
      event_id: envelope.event_id,
      event_type: eventType,
      source_event_key: envelope.source_event_key,
      captured_at: new Date().toISOString(),
      payload: rawPayload,
    },
    config.rawSpoolEncryptionKey,
    config.rawSpoolKeyId,
  );
  return {
    workspace_id: config.workspaceId,
    source_event_hash: sha256Canonical({
      source: "openclaw-plugin",
      source_event_key: envelope.source_event_key,
      event_type: eventType,
    }),
    source_kind: "live_hook",
    source_id: eventType,
    session_id: ctx.sessionId ?? null,
    turn_id: ctx.turnId ?? null,
    raw_kind: rawKindForEvent(eventType, payload),
    content_hash: sha256Canonical(rawPayload),
    sensitivity_level: sensitivityLevelForPayload(rawPayload),
    taint,
    retention_until: new Date(Date.now() + config.rawSpoolRetentionMs).toISOString(),
    encryption_key_id: config.rawSpoolKeyId,
    encrypted_payload: encryptedPayload,
    compression: "none",
    capture_policy_id: "plugin.raw-capture.v1",
    redaction_policy_id: "plugin.secret-mask.v1",
    access_policy: {
      browser_exposure: "forbidden",
      guarded_reveal_required: true,
      raw_capture_requires_plugin_handshake: true,
    },
  };
}

export function buildRawSpoolEnvelope({ eventType, payload, trust, taint = [], ctx = {}, config, envelope }) {
  const rawPayload = redactPayload(payload ?? {}, { captureRawConversation: true });
  return {
    ...envelope,
    trust,
    taint,
    session_id: ctx.sessionId ?? envelope.session_id ?? null,
    turn_id: ctx.turnId ?? envelope.turn_id ?? null,
    event_type: eventType,
    evidence_fidelity: "raw_vault_linked",
    payload: rawPayload,
    payload_hash: payloadHashForPayload(rawPayload),
    raw_evidence_record_id: null,
    workspace_id: config.workspaceId,
  };
}

export function redactEventForForward(event) {
  const payload = redactPayload(event?.payload ?? {}, { captureRawConversation: false });
  return {
    ...event,
    payload,
    payload_hash: payloadHashForPayload(payload),
    redaction_state: "redacted",
    evidence_fidelity:
      event?.raw_evidence_record_id && event.evidence_fidelity === "raw_vault_linked"
        ? "raw_vault_linked"
        : downgradeFidelity(event?.evidence_fidelity),
  };
}

export function payloadHashForPayload(payload) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex")}`;
}

function encryptJson(value, secret, keyId) {
  if (!secret) {
    throw new Error("raw evidence encryption key is required");
  }
  const key = crypto.createHash("sha256").update(String(secret)).digest();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(value), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return {
    algorithm: "aes-256-gcm",
    key_id: keyId,
    iv: iv.toString("base64"),
    auth_tag: cipher.getAuthTag().toString("base64"),
    ciphertext: ciphertext.toString("base64"),
  };
}

function rawKindForEvent(eventType, payload) {
  if (eventType === "llm_input") {
    return "model_input";
  }
  if (eventType === "llm_output") {
    return "model_output";
  }
  if (eventType === "tool_call_start") {
    return "tool_params";
  }
  if (eventType === "tool_call_end" || eventType === "tool_result_persist") {
    return "tool_result";
  }
  if (eventType === "message_received") {
    return "user_prompt";
  }
  if (eventType === "message_sent") {
    return "agent_message";
  }
  if (payload?.systemPrompt || payload?.system_prompt) {
    return "system_prompt";
  }
  return "other";
}

function sensitivityLevelForPayload(payload) {
  const encoded = JSON.stringify(payload);
  if (/\[REDACTED\]/.test(encoded)) {
    return "secret_candidate";
  }
  return "private";
}

function downgradeFidelity(value) {
  if (value === "metadata_only" || value === "hash_only") {
    return value;
  }
  return "redacted_derivative";
}

function sha256Canonical(value) {
  return `sha256:${crypto.createHash("sha256").update(canonicalJson(value)).digest("hex")}`;
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}
