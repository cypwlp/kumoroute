// Tiny CDP client: measures layout in headless Edge/Chrome without extra deps.
// Usage: node scripts/measure.mjs <url> "<js expression>"
const [url, expr] = process.argv.slice(2);
const PORT = process.env.CDP_PORT || 9333;

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    pending.set(msgId, { resolve, reject });
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}

ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
  }
});

await new Promise((resolve) => ws.addEventListener("open", resolve));
await send("Page.enable");
if (process.env.VIEWPORT) {
  const [width, height] = process.env.VIEWPORT.split("x").map(Number);
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 700,
  });
}
await send("Page.navigate", { url });
await new Promise((r) => setTimeout(r, 2500));
const result = await send("Runtime.evaluate", {
  expression: expr,
  returnByValue: true,
  awaitPromise: true,
});
console.log(JSON.stringify(result.result?.value ?? result, null, 2));
await send("Target.closeTarget", { targetId: list.id }).catch(() => {});
ws.close();
