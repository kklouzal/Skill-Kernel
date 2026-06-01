import fs from "node:fs/promises";
import path from "node:path";

export async function appendSpool(spoolDir, event, { maxBytes = 10 * 1024 * 1024 } = {}) {
  await fs.mkdir(spoolDir, { recursive: true });
  const day = new Date().toISOString().slice(0, 10);
  const file = path.join(spoolDir, `${day}.jsonl`);
  await fs.appendFile(file, `${JSON.stringify(event)}\n`, "utf8");
  await compactSpool(spoolDir, { maxBytes });
  return file;
}

export async function replaySpool(
  spoolDir,
  { batchSize = 25, maxBytes = 10 * 1024 * 1024, send } = {},
) {
  if (typeof send !== "function") {
    throw new TypeError("replaySpool requires a send function");
  }

  await compactSpool(spoolDir, { maxBytes });
  const files = await listSpoolFiles(spoolDir);
  let sent = 0;
  let failed = 0;

  for (const file of files) {
    const records = await readSpoolFile(file);
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

  return { sent, failed };
}

async function readSpoolFile(file) {
  const content = await fs.readFile(file, "utf8");
  const records = [];
  for (const raw of content.split("\n")) {
    if (!raw.trim()) {
      continue;
    }
    try {
      records.push({ raw, event: JSON.parse(raw) });
    } catch {
      records.push({ raw, event: null });
    }
  }
  return records.filter((record) => record.event !== null);
}

async function writeSpoolFile(file, rawLines) {
  await fs.writeFile(file, `${rawLines.join("\n")}\n`, "utf8");
}

export async function compactSpool(spoolDir, { maxBytes = 10 * 1024 * 1024 } = {}) {
  const files = await listSpoolFiles(spoolDir);
  let sizes = [];
  for (const file of files) {
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
