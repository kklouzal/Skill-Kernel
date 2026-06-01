import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "llm_input",
    payload: event,
    trust: "user_instruction",
    taint: ["llm_input", "runtime"],
    hookContext: ctx,
  });
}

