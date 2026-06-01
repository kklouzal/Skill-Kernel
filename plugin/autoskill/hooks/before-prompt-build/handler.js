import { maybeContextHint } from "../../src/index.js";

export default async function handler(event, ctx) {
  return maybeContextHint({ prompt: event?.prompt, hookContext: ctx });
}

