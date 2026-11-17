// Field-ish performance audit over CDP: throttled load + Web Vitals.
// Usage: node scripts/audit.mjs <url> [mobile|desktop]
const [url, mode = "mobile"] = process.argv.slice(2);
const PORT = process.env.CDP_PORT || 9333;
const mobile = mode === "mobile";
const viewport = mobile ? { width: 390, height: 844 } : { width: 1366, height: 768 };

const target = await (
  await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent("about:blank")}`, {
    method: "PUT",
  })
).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const resources = [];
let bytes = 0;

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const msgId = ++id;
    pending.set(msgId, { resolve, reject });
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });

ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.method === "Network.loadingFinished") {
    bytes += msg.params.encodedDataLength;
    return;
  }
  if (msg.method === "Network.responseReceived") {
    const r = msg.params.response;
    resources.push({ url: r.url, type: msg.params.type, mime: r.mimeType, status: r.status });
    return;
  }
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
  }
});

await new Promise((resolve) => ws.addEventListener("open", resolve));
await send("Page.enable");
await send("Network.enable");
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `window.__vitals = { lcp: 0, lcpEl: "", cls: 0 };
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      window.__vitals.lcp = e.startTime;
      window.__vitals.lcpEl = (e.element && e.element.tagName) || e.url || "";
    }
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) window.__vitals.cls += e.value;
  }).observe({ type: "layout-shift", buffered: true });`,
});
await send("Network.emulateNetworkConditions", {
  offline: false,
  latency: 150,
  downloadThroughput: (1.6 * 1024 * 1024) / 8,
  uploadThroughput: (750 * 1024) / 8,
});
await send("Emulation.setCPUThrottlingRate", { rate: 4 });
await send("Emulation.setDeviceMetricsOverride", {
  width: viewport.width,
  height: viewport.height,
  deviceScaleFactor: mobile ? 2 : 1,
  mobile,
});
await send("Page.navigate", { url });
await new Promise((r) => setTimeout(r, 6000));

const vitals = await send("Runtime.evaluate", {
  awaitPromise: true,
  returnByValue: true,
  expression: `(() => new Promise((resolve) => {
    const out = { lcp: window.__vitals.lcp, lcpEl: window.__vitals.lcpEl, cls: window.__vitals.cls, fcp: 0, longTasks: 0 };
    for (const e of performance.getEntriesByType("paint")) {
      if (e.name === "first-contentful-paint") out.fcp = e.startTime;
    }
    for (const e of performance.getEntriesByType("layout-shift")) {
      if (!e.hadRecentInput) out.cls += 0;
    }
    for (const e of performance.getEntriesByType("longtask")) out.longTasks += 1;
    const nav = performance.getEntriesByType("navigation")[0] || {};
    out.domInteractive = nav.domInteractive || 0;
    out.loadEvent = nav.loadEventEnd || 0;
    out.transferKB = 0;
    for (const r of performance.getEntriesByType("resource")) {
      out.transferKB += (r.transferSize || 0) / 1024;
    }
    resolve(out);
  }))()`,
});

const v = vitals.result.value;
const heavy = resources
  .filter((r) => r.type !== "Other")
  .map((r) => r.url.split("/").pop())
  .slice(0, 20);

console.log(
  JSON.stringify(
    {
      url,
      mode,
      fcpMs: Math.round(v.fcp),
      lcpMs: Math.round(v.lcp),
      lcpElement: v.lcpEl,
      cls: Number(v.cls.toFixed(4)),
      longTasks: v.longTasks,
      domInteractiveMs: Math.round(v.domInteractive),
      loadMs: Math.round(v.loadEvent),
      requests: resources.length,
      cdpBytesKB: Math.round(bytes / 1024),
      resources: heavy,
    },
    null,
    2,
  ),
);
ws.close();
