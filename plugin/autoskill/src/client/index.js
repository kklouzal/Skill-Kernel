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
