import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "message_sent",
    payload: event,
    trust: "agent_output",
    taint: ["message"],
    hookContext: ctx,
  });
}

