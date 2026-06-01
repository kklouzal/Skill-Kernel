import fs from "node:fs/promises";
import path from "node:path";

export async function appendSpool(spoolDir, event) {
  await fs.mkdir(spoolDir, { recursive: true });
  const day = new Date().toISOString().slice(0, 10);
  const file = path.join(spoolDir, `${day}.jsonl`);
  await fs.appendFile(file, `${JSON.stringify(event)}\n`, "utf8");
  return file;
}

