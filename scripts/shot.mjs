// Viewport-emulated screenshot via CDP (no extra deps).
// Usage: VIEWPORT=390x844 OUT=.tmp/shots/mobile.png node scripts/shot.mjs <url>
const [url] = process.argv.slice(2);
const PORT = process.env.CDP_PORT || 9333;
const OUT = process.env.OUT || ".tmp/shots/shot.png";
const [width, height] = (process.env.VIEWPORT || "1280x900").split("x").map(Number);
const full = process.env.FULL === "1";

const fs = await import("node:fs/promises");
const target = await (
  await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent("about:blank")}`, {
    method: "PUT",
  })
).json();

const ws = new WebSocket(target.webSocketDebuggerUrl);
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
await send("Emulation.setDeviceMetricsOverride", {
  width,
  height,
  deviceScaleFactor: 1,
  mobile: width < 700,
});
await send("Page.navigate", { url });
await new Promise((r) => setTimeout(r, 2000));
if (process.env.EVAL) {
  await send("Runtime.evaluate", { expression: process.env.EVAL, awaitPromise: true });
  await new Promise((r) => setTimeout(r, 500));
}
const shot = await send("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: full,
});
await fs.writeFile(OUT, Buffer.from(shot.data, "base64"));
console.log(`${OUT} ${width}x${height} ${full ? "full" : "viewport"}`);
ws.close();
