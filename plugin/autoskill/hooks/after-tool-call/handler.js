import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "tool_call_end",
    payload: event,
    trust: "tool_output",
    taint: ["tool_output", "runtime"],
    hookContext: ctx,
  });
}

