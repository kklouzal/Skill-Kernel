export async function postJson(url, payload, { timeoutMs = 150, authToken } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = { "content-type": "application/json" };
  if (authToken) {
    headers.authorization = `Bearer ${authToken}`;
  }
  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`sidecar returned ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function getJson(url, { timeoutMs = 150, authToken } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = {};
  if (authToken) {
    headers.authorization = `Bearer ${authToken}`;
  }
  try {
    const response = await fetch(url, {
      method: "GET",
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`sidecar returned ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchCoreCompatibility(sidecarUrl, options = {}) {
  const base = sidecarUrl.replace(/\/$/, "");
  const [version, capabilities, readModelContract, ready] = await Promise.all([
    getJson(`${base}/v1/version`, options),
    getJson(`${base}/v1/capabilities`, options),
    getJson(`${base}/v1/read-model-contract`, options),
    getJson(`${base}/v1/health/ready`, options),
  ]);
  return assessCoreCompatibility({
    version,
    capabilities,
    readModelContract,
    ready,
  });
}

export function assessCoreCompatibility({ version, capabilities, readModelContract, ready }) {
  const capabilityMap = capabilities?.capabilities ?? {};
  const ingestContract = capabilityMap.ingest_contract ?? {};
  const rawVaultPolicy = capabilityMap.raw_vault_policy ?? {};
  const redactionPolicy = capabilityMap.redaction_policy ?? {};
  const contentPolicy = readModelContract?.contract?.content_policy ?? {};
  const checks = [
    [version?.service === "skillkernel-core", "version.service"],
    [version?.api_contract_version === "skillkernel.api.v1", "version.api_contract_version"],
    [version?.read_model_contract_version === "skillkernel.readmodels.v1", "version.read_model_contract_version"],
    [capabilityMap.ingest === true, "capabilities.ingest"],
    [ingestContract.path === "/v1/ingest/events", "capabilities.ingest_contract.path"],
    [ingestContract.method === "POST", "capabilities.ingest_contract.method"],
    [ingestContract.auth_mode === "bearer", "capabilities.ingest_contract.auth_mode"],
    [rawVaultPolicy.raw_capture_supported === true, "capabilities.raw_vault_policy.raw_capture_supported"],
    [rawVaultPolicy.browser_exposure === "forbidden", "capabilities.raw_vault_policy.browser_exposure"],
    [redactionPolicy.plugin_redacts_before_forward === true, "capabilities.redaction_policy.plugin_redacts_before_forward"],
    [redactionPolicy.secret_redaction_required === true, "capabilities.redaction_policy.secret_redaction_required"],
    [contentPolicy.raw_content_default === "denied", "read_model_contract.content_policy.raw_content_default"],
    [contentPolicy.live_stream_raw_content === "forbidden", "read_model_contract.content_policy.live_stream_raw_content"],
    [ready?.checks?.event_ingest_api === true, "ready.checks.event_ingest_api"],
  ];
  const missing = checks.filter(([passed]) => !passed).map(([, name]) => name);
  return {
    compatible: missing.length === 0,
    reason: missing.length === 0 ? "compatible" : `missing_or_incompatible:${missing.join(",")}`,
    version,
    capabilities,
    readModelContract,
    ready,
  };
}

export async function forwardEvent(sidecarUrl, event, options = {}) {
  return forwardEvents(sidecarUrl, [event], options);
}

export async function forwardEvents(sidecarUrl, events, options = {}) {
  return postJson(
    `${sidecarUrl.replace(/\/$/, "")}/v1/ingest/events`,
    { events: events.map(normalizeEventForSidecar) },
    options,
  );
}

function normalizeEventForSidecar(event) {
  if (event?.trust === "trusted") {
    return { ...event, trust: "system_owned" };
  }
  if (event?.trust === "untrusted") {
    return { ...event, trust: "external_content" };
  }
  return event;
}

export async function fetchContextHint(sidecarUrl, request, options = {}) {
  return postJson(`${sidecarUrl.replace(/\/$/, "")}/v1/runtime/context-hint`, request, options);
}

export async function recordActionAttributionCheck(sidecarUrl, request, options = {}) {
  return postJson(
    `${sidecarUrl.replace(/\/$/, "")}/v1/attribution/action-checks`,
    request,
    options,
  );
}

export async function fetchStatus(sidecarUrl, options = {}) {
  return getJson(`${sidecarUrl.replace(/\/$/, "")}/v1/status`, options);
}
