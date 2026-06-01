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
  assert.deepEqual(result, { sent: 2, failed: 0 });
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

  assert.deepEqual(result, { sent: 0, failed: 1 });
  const files = await fs.readdir(spoolDir);
  assert.equal(files.length, 1);
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
