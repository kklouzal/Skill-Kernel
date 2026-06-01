import path from "node:path";

export function resolveConfig(ctx = {}) {
  const cfg = ctx.config?.plugins?.entries?.autoskill?.config ?? ctx.config?.autoskill ?? {};
  const workspaceDir = ctx.workspaceDir ?? process.cwd();
  return {
    enabled: cfg.enabled !== false,
    sidecarUrl: cfg.sidecarUrl ?? "http://127.0.0.1:8765",
    workspaceId: cfg.workspaceId ?? "auto",
    spoolDir: cfg.spoolDir ?? path.join(workspaceDir, ".autoskill", "spool"),
    captureRawConversation: cfg.captureRawConversation === true,
    runtimeContextBroker: {
      enabled: cfg.runtimeContextBroker?.enabled === true,
      timeoutMs: cfg.runtimeContextBroker?.timeoutMs ?? 150,
      maxTokens: cfg.runtimeContextBroker?.maxTokens ?? 600,
      failSoft: cfg.runtimeContextBroker?.failSoft !== false,
    },
  };
}

