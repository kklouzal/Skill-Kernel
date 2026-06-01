import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "tool_call_start",
    payload: event,
    trust: "tool_output",
    taint: ["tool_input", "runtime"],
    hookContext: ctx,
  });
}

