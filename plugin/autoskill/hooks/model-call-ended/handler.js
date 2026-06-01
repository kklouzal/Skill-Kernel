import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "model_call_ended",
    payload: event,
    trust: "tool_output",
    taint: ["runtime"],
    hookContext: ctx,
  });
}

