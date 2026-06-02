import { beforeToolCall } from "../../src/index.js";

export default async function handler(event, ctx) {
  return beforeToolCall(event, ctx);
}
