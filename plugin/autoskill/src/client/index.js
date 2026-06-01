export async function postJson(url, payload, { timeoutMs = 150 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
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

export async function forwardEvent(sidecarUrl, event, options = {}) {
  return postJson(`${sidecarUrl.replace(/\/$/, "")}/v1/ingest/events`, { events: [event] }, options);
}

export async function fetchContextHint(sidecarUrl, request, options = {}) {
  return postJson(`${sidecarUrl.replace(/\/$/, "")}/v1/runtime/context-hint`, request, options);
}

