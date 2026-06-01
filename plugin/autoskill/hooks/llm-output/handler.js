import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "llm_output",
    payload: event,
    trust: "agent_output",
    taint: ["llm_output", "runtime"],
    hookContext: ctx,
  });
}

