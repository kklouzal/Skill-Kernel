import fs from "node:fs/promises";
import crypto from "node:crypto";
import path from "node:path";

const SPOOL_RECORD_SCHEMA = "autoskill.plugin-spool-record.v1";
const SPOOL_TOMBSTONE_SCHEMA = "autoskill.plugin-spool-tombstone.v1";
const RAW_SPOOL_DEFAULT_RETENTION_MS = 24 * 60 * 60 * 1000;

export async function appendSpool(
  spoolDir,
  event,
  {
    maxBytes = 10 * 1024 * 1024,
    rawContent = false,
    rawContentEncryptionKey = null,
    rawContentKeyId = "plugin-local-raw-spool-v1",
    rawContentRetentionMs = RAW_SPOOL_DEFAULT_RETENTION_MS,
  } = {},
) {
  await fs.mkdir(spoolDir, { recursive: true });
  const day = new Date().toISOString().slice(0, 10);
  const file = path.join(spoolDir, `${day}.jsonl`);
  const record = buildSpoolRecord(event, {
    rawContent,
    rawContentEncryptionKey,
    rawContentKeyId,
    rawContentRetentionMs,
  });
  await fs.appendFile(file, `${JSON.stringify(record)}\n`, "utf8");
  await compactSpool(spoolDir, { maxBytes });
  return file;
}

export async function replaySpool(
  spoolDir,
  { batchSize = 25, maxBytes = 10 * 1024 * 1024, rawContentEncryptionKey = null, send } = {},
) {
  if (typeof send !== "function") {
    throw new TypeError("replaySpool requires a send function");
  }

  await compactSpool(spoolDir, { maxBytes });
  const files = await listSpoolFiles(spoolDir);
  let sent = 0;
  let failed = 0;
  let invalid = 0;

  for (const file of files) {
    const { valid, invalid: invalidRecords } = await readSpoolFile(file, {
      rawContentEncryptionKey,
    });
    invalid += invalidRecords.length;
    if (invalidRecords.length > 0) {
      await tombstoneRecords(file, invalidRecords);
    }
    const records = valid;
    if (records.length === 0) {
      await fs.rm(file, { force: true });
      continue;
    }

    const batch = records.slice(0, batchSize);
    try {
      const result = await send(batch.map((record) => record.event));
      const accepted = Number(result?.accepted ?? 0);
      const duplicate = Number(result?.duplicate ?? 0);
      const handled = accepted + duplicate;
      if (handled < batch.length) {
        failed += batch.length - handled;
        break;
      }

      sent += handled;
      const remaining = records.slice(batch.length);
      if (remaining.length === 0) {
        await fs.rm(file, { force: true });
      } else {
        await writeSpoolFile(file, remaining.map((record) => record.raw));
      }
    } catch {
      failed += batch.length;
      break;
    }
  }

  return { sent, failed, invalid };
}

async function readSpoolFile(file, { rawContentEncryptionKey = null } = {}) {
  const content = await fs.readFile(file, "utf8");
  const valid = [];
  const invalid = [];
  for (const raw of content.split("\n")) {
    if (!raw.trim()) {
      continue;
    }
    const record = decodeSpoolRecord(raw, { rawContentEncryptionKey });
    if (record.event !== null) {
      valid.push(record);
    } else {
      invalid.push(record);
    }
  }
  return { valid, invalid };
}

async function writeSpoolFile(file, rawLines) {
  await fs.writeFile(file, `${rawLines.join("\n")}\n`, "utf8");
}

export async function compactSpool(spoolDir, { maxBytes = 10 * 1024 * 1024 } = {}) {
  const files = await listSpoolFiles(spoolDir);
  for (const file of files) {
    await expireRetainedRecords(file);
  }
  let sizes = [];
  for (const file of await listSpoolFiles(spoolDir)) {
    const stat = await fs.stat(file);
    sizes.push({ file, size: stat.size });
  }

  let total = sizes.reduce((sum, item) => sum + item.size, 0);
  while (total > maxBytes && sizes.length > 0) {
    const oldest = sizes.shift();
    await fs.rm(oldest.file, { force: true });
    total -= oldest.size;
  }

  return { bytes: Math.max(total, 0), files: sizes.length };
}

export async function getSpoolStats(spoolDir) {
  const files = await listSpoolFiles(spoolDir);
  let bytes = 0;
  for (const file of files) {
    const stat = await fs.stat(file);
    bytes += stat.size;
  }
  return { files: files.length, bytes };
}

async function listSpoolFiles(spoolDir) {
  try {
    const entries = await fs.readdir(spoolDir, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".jsonl"))
      .map((entry) => path.join(spoolDir, entry.name))
      .sort();
  } catch (error) {
    if (error?.code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

function buildSpoolRecord(
  event,
  {
    rawContent = false,
    rawContentEncryptionKey = null,
    rawContentKeyId = "plugin-local-raw-spool-v1",
    rawContentRetentionMs = RAW_SPOOL_DEFAULT_RETENTION_MS,
  } = {},
) {
  const eventChecksum = sha256(canonicalJson(event));
  const base = {
    schema_version: SPOOL_RECORD_SCHEMA,
    event_id: event?.event_id ?? null,
    idempotency_key: idempotencyKey(event),
    event_checksum: eventChecksum,
    checksum_algorithm: "sha256-canonical-json-v1",
    created_at: new Date().toISOString(),
  };
  if (rawContent) {
    if (!rawContentEncryptionKey) {
      throw new Error("raw-content spool requires an encryption key");
    }
    return {
      ...base,
      storage_class: "raw_content_encrypted",
      retention_until: new Date(Date.now() + rawContentRetentionMs).toISOString(),
      encrypted_event: encryptEvent(event, rawContentEncryptionKey, rawContentKeyId),
    };
  }
  return {
    ...base,
    storage_class: "normal",
    retention_until: null,
    event,
  };
}

function decodeSpoolRecord(raw, { rawContentEncryptionKey = null } = {}) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return invalidRecord(raw, "invalid_json");
  }
  if (parsed?.schema_version !== SPOOL_RECORD_SCHEMA) {
    return { raw, event: parsed, legacy: true };
  }

  const retentionUntil = Date.parse(parsed.retention_until ?? "");
  if (Number.isFinite(retentionUntil) && retentionUntil <= Date.now()) {
    return invalidRecord(raw, "retention_expired", parsed);
  }

  let event;
  if (parsed.storage_class === "normal") {
    event = parsed.event;
  } else if (parsed.storage_class === "raw_content_encrypted") {
    if (!rawContentEncryptionKey) {
      return invalidRecord(raw, "raw_content_encryption_key_missing", parsed);
    }
    try {
      event = decryptEvent(parsed.encrypted_event, rawContentEncryptionKey);
    } catch {
      return invalidRecord(raw, "raw_content_decryption_failed", parsed);
    }
  } else {
    return invalidRecord(raw, "unknown_storage_class", parsed);
  }

  if (!event || sha256(canonicalJson(event)) !== parsed.event_checksum) {
    return invalidRecord(raw, "checksum_mismatch", parsed);
  }
  return { raw, event, legacy: false };
}

async function expireRetainedRecords(file) {
  let content;
  try {
    content = await fs.readFile(file, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") {
      return;
    }
    throw error;
  }
  const retained = [];
  const expired = [];
  for (const raw of content.split("\n")) {
    if (!raw.trim()) {
      continue;
    }
    const parsed = safeParseJson(raw);
    const retentionUntil = Date.parse(parsed?.retention_until ?? "");
    if (
      parsed?.schema_version === SPOOL_RECORD_SCHEMA &&
      parsed?.storage_class === "raw_content_encrypted" &&
      Number.isFinite(retentionUntil) &&
      retentionUntil <= Date.now()
    ) {
      expired.push(invalidRecord(raw, "retention_expired", parsed));
    } else {
      retained.push(raw);
    }
  }
  if (expired.length === 0) {
    return;
  }
  await tombstoneRecords(file, expired);
  if (retained.length === 0) {
    await fs.rm(file, { force: true });
  } else {
    await writeSpoolFile(file, retained);
  }
}

async function tombstoneRecords(file, records) {
  if (records.length === 0) {
    return;
  }
  const tombstoneFile = `${file}.corrupt`;
  const lines = records.map((record) =>
    JSON.stringify({
      schema_version: SPOOL_TOMBSTONE_SCHEMA,
      reason: record.reason,
      event_id: record.parsed?.event_id ?? null,
      idempotency_key: record.parsed?.idempotency_key ?? null,
      raw_sha256: sha256(record.raw),
      detected_at: new Date().toISOString(),
    }),
  );
  await fs.appendFile(tombstoneFile, `${lines.join("\n")}\n`, "utf8");
}

function encryptEvent(event, secret, keyId) {
  const key = crypto.createHash("sha256").update(String(secret)).digest();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(event), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return {
    algorithm: "aes-256-gcm",
    key_id: keyId,
    iv: iv.toString("base64"),
    auth_tag: cipher.getAuthTag().toString("base64"),
    ciphertext: ciphertext.toString("base64"),
  };
}

function decryptEvent(encrypted, secret) {
  if (encrypted?.algorithm !== "aes-256-gcm") {
    throw new Error("unsupported raw spool encryption algorithm");
  }
  const key = crypto.createHash("sha256").update(String(secret)).digest();
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    key,
    Buffer.from(encrypted.iv, "base64"),
  );
  decipher.setAuthTag(Buffer.from(encrypted.auth_tag, "base64"));
  const plaintext = Buffer.concat([
    decipher.update(Buffer.from(encrypted.ciphertext, "base64")),
    decipher.final(),
  ]);
  return JSON.parse(plaintext.toString("utf8"));
}

function idempotencyKey(event) {
  if (event?.event_id) {
    return `event:${event.event_id}`;
  }
  return `event-sha256:${sha256(canonicalJson(event))}`;
}

function invalidRecord(raw, reason, parsed = null) {
  return { raw, event: null, reason, parsed };
}

function safeParseJson(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
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
