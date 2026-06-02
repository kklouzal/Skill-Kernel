import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "message_received",
    payload: event,
    trust: "external_content",
    taint: ["message"],
    hookContext: ctx,
  });
}
