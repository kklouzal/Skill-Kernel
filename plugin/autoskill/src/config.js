import path from "node:path";

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
    sidecarUrl: cfg.sidecarUrl ?? "http://127.0.0.1:8765",
    ingestToken:
      cfg.ingestToken ??
      process.env.AUTOSKILL_PLUGIN_INGEST_TOKEN ??
      process.env.AUTOSKILL_INGEST_TOKEN ??
      null,
    workspaceId: cfg.workspaceId ?? "auto",
    spoolDir: cfg.spoolDir ?? path.join(workspaceDir, ".autoskill", "spool"),
    replayBatchSize: cfg.replayBatchSize ?? 25,
    maxSpoolBytes: cfg.maxSpoolBytes ?? 10 * 1024 * 1024,
    captureRawConversation: cfg.captureRawConversation === true,
    runtimeContextBroker: {
      enabled: cfg.runtimeContextBroker?.enabled === true,
      timeoutMs: cfg.runtimeContextBroker?.timeoutMs ?? 150,
      maxTokens: cfg.runtimeContextBroker?.maxTokens ?? 600,
      failSoft: cfg.runtimeContextBroker?.failSoft !== false,
    },
    runtimeToolBoundary: {
      enabled: cfg.runtimeToolBoundary?.enabled === true,
      blockOnHighRisk: cfg.runtimeToolBoundary?.blockOnHighRisk !== false,
    },
  };
}
