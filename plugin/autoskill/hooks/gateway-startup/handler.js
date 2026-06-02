import { captureEvent } from "../../src/index.js";

export default async function handler(event, ctx) {
  await captureEvent({
    eventType: "gateway_startup",
    payload: event,
    trust: "system_owned",
    taint: ["runtime"],
    hookContext: ctx,
  });
}
