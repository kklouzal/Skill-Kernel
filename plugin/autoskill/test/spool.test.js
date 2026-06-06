import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { appendSpool, compactSpool, replaySpool } from "../src/spool/index.js";

async function tempSpool() {
  return fs.mkdtemp(path.join(os.tmpdir(), "autoskill-spool-"));
}

function event(id) {
  return {
    event_id: id,
    schema_version: 1,
    workspace_id: "dev-01",
    event_type: "tool_call_end",
    occurred_at: new Date().toISOString(),
    source: "openclaw-plugin",
    trust: "tool_output",
    taint: [],
    redaction_state: "redacted",
    payload_hash: id,
    payload: { id },
  };
}

test("replaySpool sends oldest events and removes handled records", async () => {
  const spoolDir = await tempSpool();
  await appendSpool(spoolDir, event("one"));
  await appendSpool(spoolDir, event("two"));

  const sent = [];
  const result = await replaySpool(spoolDir, {
    batchSize: 10,
    send: async (events) => {
      sent.push(...events.map((item) => item.event_id));
      return { accepted: events.length, duplicate: 0 };
    },
  });

  assert.deepEqual(sent, ["one", "two"]);
  assert.deepEqual(result, { sent: 2, failed: 0, invalid: 0 });
  assert.deepEqual(await fs.readdir(spoolDir), []);
});

test("replaySpool keeps unhandled records after a partial batch", async () => {
  const spoolDir = await tempSpool();
  await appendSpool(spoolDir, event("one"));
  await appendSpool(spoolDir, event("two"));

  const result = await replaySpool(spoolDir, {
    batchSize: 2,
    send: async () => ({ accepted: 1, duplicate: 0 }),
  });

  assert.deepEqual(result, { sent: 0, failed: 1, invalid: 0 });
  const files = await fs.readdir(spoolDir);
  assert.equal(files.length, 1);
});

test("appendSpool wraps events with checksum and idempotency metadata", async () => {
  const spoolDir = await tempSpool();
  await appendSpool(spoolDir, event("one"));

  const files = await fs.readdir(spoolDir);
  const record = JSON.parse(await fs.readFile(path.join(spoolDir, files[0]), "utf8"));

  assert.equal(record.schema_version, "autoskill.plugin-spool-record.v1");
  assert.equal(record.storage_class, "normal");
  assert.equal(record.idempotency_key, "event:one");
  assert.equal(record.checksum_algorithm, "sha256-canonical-json-v1");
  assert.match(record.event_checksum, /^[0-9a-f]{64}$/);
  assert.equal(record.event.event_id, "one");
});

test("replaySpool tombstones tampered wrapped records", async () => {
  const spoolDir = await tempSpool();
  await appendSpool(spoolDir, event("one"));
  const files = await fs.readdir(spoolDir);
  const file = path.join(spoolDir, files[0]);
  const record = JSON.parse(await fs.readFile(file, "utf8"));
  record.event.event_id = "tampered";
  await fs.writeFile(file, `${JSON.stringify(record)}\n`, "utf8");

  const result = await replaySpool(spoolDir, {
    send: async () => ({ accepted: 1, duplicate: 0 }),
  });

  assert.deepEqual(result, { sent: 0, failed: 0, invalid: 1 });
  assert.deepEqual(await fs.readdir(spoolDir), [`${files[0]}.corrupt`]);
  const tombstone = JSON.parse(await fs.readFile(`${file}.corrupt`, "utf8"));
  assert.equal(tombstone.schema_version, "autoskill.plugin-spool-tombstone.v1");
  assert.equal(tombstone.reason, "checksum_mismatch");
  assert.equal(tombstone.event_id, "one");
});

test("raw-content spool records are encrypted at rest and replayable with the key", async () => {
  const spoolDir = await tempSpool();
  const rawEvent = event("raw-one");
  rawEvent.payload.systemPrompt = "private prompt";
  await appendSpool(spoolDir, rawEvent, {
    rawContent: true,
    rawContentEncryptionKey: "local-test-key",
    rawContentRetentionMs: 60_000,
  });

  const files = await fs.readdir(spoolDir);
  const content = await fs.readFile(path.join(spoolDir, files[0]), "utf8");
  const record = JSON.parse(content);
  assert.equal(record.storage_class, "raw_content_encrypted");
  assert.match(record.encrypted_event.ciphertext, /^[A-Za-z0-9+/=]+$/);
  assert.equal(content.includes("private prompt"), false);

  const sent = [];
  const result = await replaySpool(spoolDir, {
    rawContentEncryptionKey: "local-test-key",
    send: async (events) => {
      sent.push(...events);
      return { accepted: events.length, duplicate: 0 };
    },
  });

  assert.deepEqual(result, { sent: 1, failed: 0, invalid: 0 });
  assert.equal(sent[0].payload.systemPrompt, "private prompt");
});

test("expired raw-content spool records are tombstoned during compaction", async () => {
  const spoolDir = await tempSpool();
  await appendSpool(spoolDir, event("expired"), {
    rawContent: true,
    rawContentEncryptionKey: "local-test-key",
    rawContentRetentionMs: -1,
  });

  const result = await compactSpool(spoolDir);
  const files = await fs.readdir(spoolDir);

  assert.deepEqual(result, { bytes: 0, files: 0 });
  assert.equal(files.length, 1);
  assert.match(files[0], /\.jsonl\.corrupt$/);
  const tombstone = JSON.parse(await fs.readFile(path.join(spoolDir, files[0]), "utf8"));
  assert.equal(tombstone.reason, "retention_expired");
});

test("compactSpool removes oldest files when the spool exceeds max bytes", async () => {
  const spoolDir = await tempSpool();
  await fs.writeFile(path.join(spoolDir, "2026-01-01.jsonl"), `${JSON.stringify(event("old"))}\n`);
  await fs.writeFile(path.join(spoolDir, "2026-01-02.jsonl"), `${JSON.stringify(event("new"))}\n`);

  const result = await compactSpool(spoolDir, { maxBytes: 120 });
  const files = await fs.readdir(spoolDir);

  assert.ok(result.bytes <= 120);
  assert.deepEqual(files, []);
});
