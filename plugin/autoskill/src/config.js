import path from "node:path";

function envBool(name) {
  const value = process.env[name];
  if (value === undefined) {
    return undefined;
  }
  if (/^(1|true|yes|on)$/i.test(value)) {
    return true;
  }
  if (/^(0|false|no|off)$/i.test(value)) {
    return false;
  }
  return undefined;
}

function envInt(name) {
  const value = process.env[name];
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function resolveConfig(ctx = {}) {
  const cfg =
    ctx.context?.pluginConfig ??
    ctx.pluginConfig ??
    ctx.config?.plugins?.entries?.autoskill?.config ??
    ctx.config?.autoskill ??
    {};
  const workspaceDir = ctx.workspaceDir ?? process.cwd();
  return {
    enabled: cfg.enabled !== false,
    sidecarUrl:
      cfg.sidecarUrl ??
      process.env.AUTOSKILL_PLUGIN_SIDECAR_URL ??
      process.env.AUTOSKILL_SIDECAR_URL ??
      "http://127.0.0.1:8765",
    ingestToken:
      cfg.ingestToken ??
      process.env.AUTOSKILL_PLUGIN_INGEST_TOKEN ??
      process.env.AUTOSKILL_INGEST_TOKEN ??
      null,
    workspaceId:
      cfg.workspaceId ??
      process.env.AUTOSKILL_PLUGIN_WORKSPACE_ID ??
      process.env.AUTOSKILL_WORKSPACE_ID ??
      "auto",
    spoolDir: cfg.spoolDir ?? path.join(workspaceDir, ".autoskill", "spool"),
    replayBatchSize: cfg.replayBatchSize ?? 25,
    maxSpoolBytes: cfg.maxSpoolBytes ?? 10 * 1024 * 1024,
    captureRawConversation:
      cfg.captureRawConversation ??
      envBool("AUTOSKILL_PLUGIN_CAPTURE_RAW_CONVERSATION") ??
      envBool("AUTOSKILL_CAPTURE_RAW_CONVERSATION") ??
      false,
    runtimeContextBroker: {
      enabled:
        cfg.runtimeContextBroker?.enabled ??
        envBool("AUTOSKILL_PLUGIN_RUNTIME_CONTEXT_BROKER_ENABLED") ??
        envBool("AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED") ??
        false,
      timeoutMs:
        cfg.runtimeContextBroker?.timeoutMs ??
        envInt("AUTOSKILL_PLUGIN_RUNTIME_CONTEXT_TIMEOUT_MS") ??
        envInt("AUTOSKILL_RUNTIME_CONTEXT_TIMEOUT_MS") ??
        150,
      maxTokens:
        cfg.runtimeContextBroker?.maxTokens ??
        envInt("AUTOSKILL_PLUGIN_MAX_CONTEXT_HINT_TOKENS") ??
        envInt("AUTOSKILL_MAX_CONTEXT_HINT_TOKENS") ??
        600,
      failSoft: cfg.runtimeContextBroker?.failSoft !== false,
    },
    runtimeToolBoundary: {
      enabled:
        cfg.runtimeToolBoundary?.enabled ??
        envBool("AUTOSKILL_PLUGIN_RUNTIME_TOOL_BOUNDARY_ENABLED") ??
        envBool("AUTOSKILL_RUNTIME_TOOL_BOUNDARY_ENABLED") ??
        false,
      blockOnHighRisk:
        cfg.runtimeToolBoundary?.blockOnHighRisk ??
        envBool("AUTOSKILL_PLUGIN_RUNTIME_TOOL_BOUNDARY_BLOCK_ON_HIGH_RISK") ??
        envBool("AUTOSKILL_RUNTIME_TOOL_BOUNDARY_BLOCK_ON_HIGH_RISK") ??
        true,
    },
  };
}
