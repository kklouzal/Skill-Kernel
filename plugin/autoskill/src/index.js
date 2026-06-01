import { fetchContextHint, forwardEvent, forwardEvents } from "./client/index.js";
import { resolveConfig } from "./config.js";
import { buildEventEnvelope } from "./event-envelope.js";
import { appendSpool, replaySpool } from "./spool/index.js";

let replayInFlight = false;

export async function captureEvent({ eventType, payload, trust, taint, hookContext }) {
  const config = resolveConfig(hookContext);
  if (!config.enabled) {
    return { captured: false, reason: "disabled" };
  }
  const envelope = buildEventEnvelope({ eventType, payload, trust, taint, ctx: hookContext, config });
  try {
    await forwardEvent(config.sidecarUrl, envelope, {
      timeoutMs: 500,
      authToken: config.ingestToken,
    });
    await replayCapturedSpool(config);
    return { captured: true, forwarded: true, eventId: envelope.event_id };
  } catch (error) {
    await appendSpool(config.spoolDir, envelope, { maxBytes: config.maxSpoolBytes });
    return {
      captured: true,
      forwarded: false,
      spooled: true,
      eventId: envelope.event_id,
      error: String(error?.message ?? error),
    };
  }
}

async function replayCapturedSpool(config) {
  if (replayInFlight) {
    return;
  }
  replayInFlight = true;
  try {
    await replaySpool(config.spoolDir, {
      batchSize: config.replayBatchSize,
      maxBytes: config.maxSpoolBytes,
      send: (events) =>
        forwardEvents(config.sidecarUrl, events, {
          timeoutMs: 1000,
          authToken: config.ingestToken,
        }),
    });
  } finally {
    replayInFlight = false;
  }
}

export async function maybeContextHint({ prompt, hookContext }) {
  const config = resolveConfig(hookContext);
  if (!config.enabled || !config.runtimeContextBroker.enabled) {
    return undefined;
  }
  try {
    const response = await fetchContextHint(
      config.sidecarUrl,
      {
        workspace_id: config.workspaceId,
        agent_id: hookContext?.agentId ?? null,
        session_id: hookContext?.sessionId ?? null,
        turn_id: hookContext?.turnId ?? null,
        user_intent: prompt ?? null,
        max_tokens: config.runtimeContextBroker.maxTokens,
      },
      { timeoutMs: config.runtimeContextBroker.timeoutMs, authToken: config.ingestToken },
    );
    if (!response?.hint) {
      return undefined;
    }
    return { appendContext: response.hint };
  } catch (error) {
    if (!config.runtimeContextBroker.failSoft) {
      throw error;
    }
    return undefined;
  }
}
