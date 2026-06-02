const SECRET_KEY_RE = /(api[_-]?key|token|secret|password|passwd|credential|authorization|cookie|session)/i;
const CONTENT_KEY_NAMES = new Set([
  "body",
  "completion",
  "content",
  "conversation",
  "input",
  "message",
  "messages",
  "output",
  "prompt",
  "rawconversation",
  "response",
  "result",
  "systemprompt",
  "text",
]);
const SECRET_PATTERNS = [
  /\bsk-[A-Za-z0-9_-]{20,}\b/g,
  /\bgh[pousr]_[A-Za-z0-9_]{20,}\b/g,
  /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/g,
  /\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b/gi,
];
const EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;

function contentKeyName(key) {
  return String(key).replace(/[^A-Za-z0-9]/g, "").toLowerCase();
}

function isContentKey(key) {
  return CONTENT_KEY_NAMES.has(contentKeyName(key));
}

function contentDigest(value) {
  return JSON.stringify(value)?.length ?? String(value).length;
}

export function redactText(value) {
  let redacted = String(value);
  for (const pattern of SECRET_PATTERNS) {
    redacted = redacted.replace(pattern, "[REDACTED]");
  }
  return redacted.replace(EMAIL_RE, "[REDACTED_EMAIL]");
}

function redactContent(value) {
  if (value === null || value === undefined) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactContent(item));
  }
  if (typeof value === "object") {
    const safe = {};
    for (const [key, item] of Object.entries(value)) {
      if (["id", "index", "name", "provider", "role", "type"].includes(contentKeyName(key))) {
        safe[key] = redactPayload(item, { captureRawConversation: false });
        continue;
      }
      safe[key] = isContentKey(key)
        ? redactContent(item)
        : redactPayload(item, { captureRawConversation: false });
    }
    return safe;
  }
  return `[REDACTED_CONTENT bytes=${contentDigest(value)}]`;
}

export function redactPayload(value, { captureRawConversation = false } = {}) {
  if (typeof value === "string") {
    return redactText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactPayload(item, { captureRawConversation }));
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      if (SECRET_KEY_RE.test(key)) {
        out[key] = "[REDACTED]";
      } else if (!captureRawConversation && isContentKey(key)) {
        out[key] = redactContent(item);
      } else {
        out[key] = redactPayload(item, { captureRawConversation });
      }
    }
    return out;
  }
  return value;
}
