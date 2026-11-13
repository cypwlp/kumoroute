"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

let demo = false;
let state = null;
let groups = [];
let groupDelays = {};
let page = "overview";
let prevTotals = null;
let sparkDown = [];
let sparkUp = [];
let toastTimer = null;
let pendingDelete = { id: null, timer: null };
let lastProxyRecovery = null;
let diagnosticsText = "";

const STATS_KEY = "kumoroute.stats.v1";
const PREFS_KEY = "kumoroute.preferences.v1";
const STATS_KEEP_DAYS = 35;
const MAX_EVENTS = 100;
let usageData = loadUsageData();
let prefs = loadPreferences();
let latestUpdate = null;
let sessionStartedAt = Date.now();
let peakConnections = 0;
let peakDownSpeed = 0;
let peakUpSpeed = 0;
let statsDirty = false;
let lastStatsSave = 0;
let lastSeenCoreRunning = null;
let lastSeenSysProxy = null;
let proxyOnSince = null;
let connectionSnapshots = new Map();
let knownGroupNames = new Set();
let clearStatsPending = false;
let clearStatsTimer = null;

/* ---------- helpers ---------- */

function fmtBytes(n, perSec) {
  n = Number(n) || 0;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  const v = i === 0 ? Math.round(n) : n >= 100 ? n.toFixed(0) : n.toFixed(1);
  return v + " " + units[i] + (perSec ? "/s" : "");
}

function localDayKey(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function loadPreferences() {
  const defaults = { autoUpdateCheck: true, lastUpdateCheck: 0 };
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    return {
      autoUpdateCheck: parsed.autoUpdateCheck !== false,
      lastUpdateCheck: Number(parsed.lastUpdateCheck || 0),
    };
  } catch (e) {
    return defaults;
  }
}

function savePreferences() {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch (e) { /* ignore */ }
}

function renderUpdateUi() {
  if (!$("#update-current")) return;
  $("#update-current").textContent = "v" + (latestUpdate?.current || (state ? state.app_version : "—"));
  $("#sw-auto-update").checked = prefs.autoUpdateCheck !== false;
  const latest = latestUpdate?.latest ? "v" + latestUpdate.latest : "尚未檢查";
  $("#update-latest").textContent = latest;
  const btn = $("#btn-open-update");
  btn.disabled = !(latestUpdate && latestUpdate.update_available && latestUpdate.url);
  if (latestUpdate && latestUpdate.update_available) {
    $("#update-status").textContent = `有新版本 ${latest} 可用。`;
  } else if (latestUpdate && latestUpdate.latest) {
    $("#update-status").textContent = "目前已是最新版本。";
  } else {
    $("#update-status").textContent = "只檢查版本並提示；不會自動下載或執行安裝檔。";
  }
}

async function checkForUpdates(manual = true) {
  if (demo) {
    latestUpdate = { ok: true, current: demoCfg.app_version, latest: demoCfg.app_version, update_available: false, url: "https://github.com/cypwlp/kumoroute/releases" };
    renderUpdateUi();
    if (manual) toast("目前已是最新版本", "ok");
    return latestUpdate;
  }
  const btn = $("#btn-check-update");
  if (btn) { btn.disabled = true; btn.textContent = "檢查中…"; }
  try {
    const res = await api("check_update");
    if (res && res.ok) {
      latestUpdate = res;
      prefs.lastUpdateCheck = Date.now();
      savePreferences();
      renderUpdateUi();
      if (res.update_available) toast(`發現新版本 v${res.latest}`, "ok");
      else if (manual) toast("目前已是最新版本", "ok");
      return res;
    }
    if (manual) toast((res && res.error) || "檢查更新失敗", "error");
  } catch (e) {
    if (manual) toast(String(e), "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "檢查更新"; }
  }
  return null;
}

function initUpdateChecker() {
  renderUpdateUi();
  if (prefs.autoUpdateCheck && Date.now() - Number(prefs.lastUpdateCheck || 0) > 6 * 3600 * 1000) {
    checkForUpdates(false);
  }
}

function installUiCrashHandlers() {
  const report = (message, stack) => {
    if (demo) return;
    if (!((window.pywebview && window.pywebview.api) || (window.__TAURI__ && window.__TAURI__.core))) return;
    api("record_ui_error", String(message || "unknown UI error"), String(stack || "")).catch(() => {});
  };
  window.addEventListener("error", (event) => report(event.message, event.error && event.error.stack));
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    report(reason && reason.message ? reason.message : reason, reason && reason.stack ? reason.stack : "");
  });
}

function emptyAttribution() {
  return { profiles: {}, groups: {}, nodes: {}, domains: {}, rules: {} };
}

function defaultUsageData() {
  return {
    days: {},
    limits: { daily: 0, weekly: 0, notifiedDay: "", notifiedWeek: "" },
    domainTracking: false,
    events: [],
    nodeHealth: {},
    attribution: emptyAttribution(),
    core: { starts: 0, restarts: 0, lastStartedAt: null },
    systemProxySeconds: 0,
    updatedAt: null,
  };
}

function loadUsageData() {
  const empty = defaultUsageData();
  try {
    const raw = localStorage.getItem(STATS_KEY);
    if (!raw) return empty;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return empty;
    const attr = parsed.attribution && typeof parsed.attribution === "object" ? parsed.attribution : {};
    return {
      days: parsed.days && typeof parsed.days === "object" && !Array.isArray(parsed.days) ? parsed.days : {},
      limits: {
        daily: Number(parsed.limits?.daily || 0),
        weekly: Number(parsed.limits?.weekly || 0),
        notifiedDay: String(parsed.limits?.notifiedDay || ""),
        notifiedWeek: String(parsed.limits?.notifiedWeek || ""),
      },
      domainTracking: !!parsed.domainTracking,
      events: Array.isArray(parsed.events) ? parsed.events.slice(-MAX_EVENTS) : [],
      nodeHealth: parsed.nodeHealth && typeof parsed.nodeHealth === "object" ? parsed.nodeHealth : {},
      attribution: {
        profiles: attr.profiles && typeof attr.profiles === "object" ? attr.profiles : {},
        groups: attr.groups && typeof attr.groups === "object" ? attr.groups : {},
        nodes: attr.nodes && typeof attr.nodes === "object" ? attr.nodes : {},
        domains: attr.domains && typeof attr.domains === "object" ? attr.domains : {},
        rules: attr.rules && typeof attr.rules === "object" ? attr.rules : {},
      },
      core: {
        starts: Number(parsed.core?.starts || 0),
        restarts: Number(parsed.core?.restarts || 0),
        lastStartedAt: parsed.core?.lastStartedAt || null,
      },
      systemProxySeconds: Number(parsed.systemProxySeconds || 0),
      updatedAt: parsed.updatedAt || null,
    };
  } catch (e) {
    return empty;
  }
}

function pruneUsageData() {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - STATS_KEEP_DAYS);
  const cutoffKey = localDayKey(cutoff);
  Object.keys(usageData.days).forEach((key) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || key < cutoffKey) delete usageData.days[key];
  });
}

function saveUsageData(force = false) {
  if (!force && !statsDirty) return;
  flushSystemProxyUptime();
  pruneUsageData();
  usageData.updatedAt = new Date().toISOString();
  try {
    localStorage.setItem(STATS_KEY, JSON.stringify(usageData));
    statsDirty = false;
    lastStatsSave = Date.now();
  } catch (e) { /* storage may be unavailable */ }
}

function addUsage(down, up) {
  if (down <= 0 && up <= 0) return;
  const key = localDayKey();
  const day = usageData.days[key] || { down: 0, up: 0 };
  day.down = Number(day.down || 0) + Math.max(0, down);
  day.up = Number(day.up || 0) + Math.max(0, up);
  usageData.days[key] = day;
  statsDirty = true;
}

function recentDays(count) {
  const out = [];
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() - i);
    const key = localDayKey(d);
    const item = usageData.days[key] || { down: 0, up: 0 };
    out.push({
      key,
      date: d,
      down: Number(item.down || 0),
      up: Number(item.up || 0),
    });
  }
  return out;
}

function fmtDuration(totalSeconds) {
  totalSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) return `${h} 小時 ${m} 分`;
  if (m > 0) return `${m} 分 ${s} 秒`;
  return `${s} 秒`;
}

function addEvent(type, title, detail = "") {
  const item = { t: new Date().toISOString(), type, title, detail };
  usageData.events.push(item);
  if (usageData.events.length > MAX_EVENTS) usageData.events.splice(0, usageData.events.length - MAX_EVENTS);
  statsDirty = true;
  if (page === "stats") renderStatsPage();
}

function flushSystemProxyUptime() {
  if (lastSeenSysProxy && proxyOnSince) {
    const now = Date.now();
    usageData.systemProxySeconds += Math.max(0, (now - proxyOnSince) / 1000);
    proxyOnSince = now;
    statsDirty = true;
  }
}

function currentSystemProxySeconds() {
  return Number(usageData.systemProxySeconds || 0) + (lastSeenSysProxy && proxyOnSince ? (Date.now() - proxyOnSince) / 1000 : 0);
}

function trackRuntimeTransitions(s) {
  const now = Date.now();
  const running = !!s.running;
  if (lastSeenCoreRunning === null) {
    lastSeenCoreRunning = running;
    if (running) {
      usageData.core.starts += 1;
      usageData.core.lastStartedAt = new Date().toISOString();
      addEvent("core", "核心已啟動", s.core_version ? "mihomo " + s.core_version : "");
    }
  } else if (running !== lastSeenCoreRunning) {
    if (running) {
      usageData.core.starts += 1;
      usageData.core.restarts += 1;
      usageData.core.lastStartedAt = new Date().toISOString();
      addEvent("core", "核心已重新啟動", s.core_version ? "mihomo " + s.core_version : "");
    } else {
      addEvent("core", "核心已停止", "");
    }
    lastSeenCoreRunning = running;
  }

  const proxyOn = !!s.sys_proxy;
  if (lastSeenSysProxy === null) {
    lastSeenSysProxy = proxyOn;
    proxyOnSince = proxyOn ? now : null;
  } else if (proxyOn !== lastSeenSysProxy) {
    if (lastSeenSysProxy && proxyOnSince) {
      usageData.systemProxySeconds += Math.max(0, (now - proxyOnSince) / 1000);
    }
    proxyOnSince = proxyOn ? now : null;
    lastSeenSysProxy = proxyOn;
    addEvent("proxy", proxyOn ? "系統代理已開啟" : "系統代理已關閉", "");
  }
}

function startOfWeekKey(date = new Date()) {
  const d = new Date(date);
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return localDayKey(d);
}

function maybeRequestNotifications() {
  try {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  } catch (e) { /* ignore */ }
}

function sendDesktopNotification(title, body) {
  try {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(title, { body, icon: "icon.png" });
    }
  } catch (e) { /* ignore */ }
}

function checkUsageLimits() {
  const daily = usageData.days[localDayKey()] || { down: 0, up: 0 };
  const weeklyTotal = recentDays(7).reduce((sum, d) => sum + d.down + d.up, 0);
  const dailyTotal = Number(daily.down || 0) + Number(daily.up || 0);
  const dayKey = localDayKey();
  const weekKey = startOfWeekKey();
  const messages = [];
  let newlyExceeded = false;

  if (usageData.limits.daily > 0 && dailyTotal >= usageData.limits.daily) {
    messages.push(`今日流量 ${fmtBytes(dailyTotal)} / 上限 ${fmtBytes(usageData.limits.daily)}`);
    if (usageData.limits.notifiedDay !== dayKey) {
      usageData.limits.notifiedDay = dayKey;
      newlyExceeded = true;
    }
  }
  if (usageData.limits.weekly > 0 && weeklyTotal >= usageData.limits.weekly) {
    messages.push(`近 7 日流量 ${fmtBytes(weeklyTotal)} / 上限 ${fmtBytes(usageData.limits.weekly)}`);
    if (usageData.limits.notifiedWeek !== weekKey) {
      usageData.limits.notifiedWeek = weekKey;
      newlyExceeded = true;
    }
  }

  const alert = $("#usage-alert");
  if (alert) {
    alert.textContent = messages.length ? messages.join(" · ") : "";
    alert.classList.toggle("hidden", !messages.length);
  }
  if (newlyExceeded) {
    const text = messages.join(" · ");
    addEvent("limit", "流量上限提醒", text);
    toast(text, "error");
    sendDesktopNotification("KumoRoute 流量提醒", text);
    statsDirty = true;
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, type = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

async function waitBridge() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve();
    if (window.__TAURI__ && window.__TAURI__.core) return resolve();
    let timer = null;
    const done = () => {
      clearTimeout(timer);
      window.removeEventListener("pywebviewready", done);
      resolve();
    };
    timer = setTimeout(done, 1600);
    window.addEventListener("pywebviewready", done);
  });
}

// Tauri invoke 需要 named（camelCase）參數；pywebview 用 positional。
const TAURI_SIG = {
  set_mode: ["mode"],
  set_system_proxy: ["enabled"],
  select_proxy: ["group", "name"],
  test_group_delay: ["group"],
  add_subscription: ["url", "name"],
  update_profile: ["pid"],
  delete_profile: ["pid"],
  set_active_profile: ["pid"],
  save_settings: ["mixedPort", "controllerPort"],
  save_stats_export: ["format", "content"],
  record_ui_error: ["message", "stack"],
  open_url: ["url"],
};

async function api(fn, ...args) {
  if (demo) return demoApi(fn, ...args);
  if (window.__TAURI__ && window.__TAURI__.core) {
    const names = TAURI_SIG[fn] || [];
    const payload = {};
    names.forEach((n, i) => (payload[n] = args[i]));
    return await window.__TAURI__.core.invoke(fn, payload);
  }
  return await window.pywebview.api[fn](...args);
}

/* ---------- demo mode ---------- */

const demoCfg = {
  running: true,
  sys_proxy: false,
  mode: "rule",
  mixed_port: 7890,
  controller_port: 9090,
  core_version: "v1.19.33",
  app_version: "0.5.2",
  data_dir: "C:\\Users\\…\\AppData\\Roaming\\KumoRoute",
  test_url: "https://cp.cloudflare.com/generate_204",
  profiles: [
    { id: "demo1", name: "範例機場", kind: "remote", updated_at: "2026-11-10 10:42:18" },
    { id: "direct", name: "內建直連（DIRECT）", kind: "builtin", updated_at: "2026-11-10 10:38:02" },
  ],
  active_profile: "demo1",
  totals: { down: 734003200, up: 28311552 },
  connections: [
    { id: "demo-c1", download: 124000000, upload: 6400000, host: "youtube.com", rule: "DomainSuffix", rulePayload: "youtube.com", chains: ["PROXY", "日本 02"] },
    { id: "demo-c2", download: 58000000, upload: 2100000, host: "github.com", rule: "DomainKeyword", rulePayload: "github", chains: ["PROXY", "香港 01"] },
    { id: "demo-c3", download: 33000000, upload: 1800000, host: "openai.com", rule: "DomainSuffix", rulePayload: "openai.com", chains: ["自動選擇", "新加坡 04"] },
  ],
  groups: null,
};

const mkNodes = (region, count, type) =>
  Array.from({ length: count }, (_, i) => ({ name: `${region} ${String(i + 1).padStart(2, "0")}`, type }));

if (!demoCfg.groups) {
  demoCfg.groups = [
    {
      name: "PROXY", type: "Selector", now: "香港 01",
      nodes: [{ name: "自動選擇", type: "URLTest" }, ...mkNodes("香港", 6, "Trojan"), ...mkNodes("日本", 6, "Shadowsocks"), ...mkNodes("新加坡", 4, "Vmess"), { name: "DIRECT", type: "Direct" }],
    },
    {
      name: "自動選擇", type: "URLTest", now: "日本 02",
      nodes: [...mkNodes("香港", 4, "Trojan"), ...mkNodes("日本", 4, "Shadowsocks"), ...mkNodes("新加坡", 2, "Vmess")],
    },
    {
      name: "串流媒體", type: "Selector", now: "DIRECT",
      nodes: [...mkNodes("新加坡", 3, "Vmess"), { name: "DIRECT", type: "Direct" }],
    },
  ];
  for (const g of demoCfg.groups) {
    groupDelays[g.name] = {};
    for (const n of g.nodes) {
      if (n.type === "Direct") continue;
      groupDelays[g.name][n.name] = Math.round(28 + Math.random() * 520);
    }
  }
}

function demoState() {
  const active = demoCfg.profiles.find((p) => p.id === demoCfg.active_profile) || demoCfg.profiles[0];
  return {
    app_version: demoCfg.app_version,
    core_version: demoCfg.running ? demoCfg.core_version : null,
    running: demoCfg.running,
    sys_proxy: demoCfg.sys_proxy,
    mode: demoCfg.mode,
    mixed_port: demoCfg.mixed_port,
    controller_port: demoCfg.controller_port,
    active_profile: active,
    profiles: demoCfg.profiles,
    data_dir: demoCfg.data_dir,
    core_found: true,
    test_url: demoCfg.test_url,
  };
}

function demoLive() {
  if (!demoCfg.running) return { running: false };
  demoCfg.totals.down += Math.random() * 900000;
  demoCfg.totals.up += Math.random() * 90000;
  demoCfg.connections.forEach((conn, index) => {
    conn.download += Math.random() * (360000 - index * 70000);
    conn.upload += Math.random() * (32000 - index * 4000);
  });
  return {
    running: true,
    down_total: Math.round(demoCfg.totals.down),
    up_total: Math.round(demoCfg.totals.up),
    count: 24 + Math.round(Math.random() * 40),
    connections: demoCfg.connections,
  };
}

async function demoApi(fn, ...args) {
  await new Promise((r) => setTimeout(r, 120));
  switch (fn) {
    case "get_state": return demoState();
    case "get_live": return demoLive();
    case "get_proxy_groups": return { ok: true, groups: demoCfg.groups };
    case "select_proxy": {
      const g = demoCfg.groups.find((x) => x.name === args[0]);
      if (g) g.now = args[1];
      return { ok: true };
    }
    case "test_group_delay": {
      const g = demoCfg.groups.find((x) => x.name === args[0]);
      const delays = {};
      if (g) for (const n of g.nodes) if (n.type !== "Direct") delays[n.name] = Math.round(25 + Math.random() * 600);
      return { ok: true, delays };
    }
    case "set_mode": demoCfg.mode = args[0]; return { ok: true };
    case "start_core": demoCfg.running = true; return { ok: true };
    case "stop_core": demoCfg.running = false; demoCfg.sys_proxy = false; prevTotals = null; return { ok: true };
    case "set_system_proxy": demoCfg.sys_proxy = !!args[0]; return { ok: true, sys_proxy: demoCfg.sys_proxy };
    case "add_subscription": {
      demoCfg.profiles.unshift({ id: "demo" + Date.now(), name: args[1] || "新訂閱", kind: "remote", updated_at: new Date().toLocaleString("zh-TW") });
      demoCfg.active_profile = demoCfg.profiles[0].id;
      return { ok: true };
    }
    case "update_profile": return { ok: true };
    case "delete_profile": {
      demoCfg.profiles = demoCfg.profiles.filter((p) => p.id !== args[0] || p.kind === "builtin");
      if (!demoCfg.profiles.some((p) => p.id === demoCfg.active_profile)) demoCfg.active_profile = demoCfg.profiles[0].id;
      return { ok: true };
    }
    case "set_active_profile": demoCfg.active_profile = args[0]; return { ok: true };
    case "import_profile": return { ok: false, cancelled: true };
    case "get_logs": return { ok: true, lines: [
      "time=\"2026-11-10T10:42:19+08:00\" level=info msg=\"Start initial configuration in progress\"",
      "time=\"2026-11-10T10:42:19+08:00\" level=info msg=\"Initial configuration completed\"",
      "time=\"2026-11-10T10:42:19+08:00\" level=info msg=\"RESTful API listening at: 127.0.0.1:9090\"",
      "time=\"2026-11-10T10:42:19+08:00\" level=info msg=\"Mixed(http+socks) proxy listening at: 127.0.0.1:7890\"",
      "time=\"2026-11-10T10:43:02+08:00\" level=info msg=\"[TCP] 192.168.1.10:52631 --> www.google.com:443 match DomainSuffix(google.com) using PROXY[香港 01]\"",
      "time=\"2026-11-10T10:43:02+08:00\" level=info msg=\"[TCP] 192.168.1.10:52633 --> api.github.com:443 match DomainKeyword(github) using PROXY[香港 01]\"",
      "time=\"2026-11-10T10:43:05+08:00\" level=warning msg=\"[DNS] resolve www.youtube.com fail: context deadline exceeded\"",
      "time=\"2026-11-10T10:43:09+08:00\" level=info msg=\"[UDP] 192.168.1.10:52640 --> 8.8.8.8:53 match Match() using PROXY[香港 01]\"",
    ] };
    case "save_settings": demoCfg.mixed_port = Number(args[0]); demoCfg.controller_port = Number(args[1]); return { ok: true };
    case "open_data_dir": return { ok: true };
    case "open_url": return { ok: true };
    default: return { ok: true };
  }
}

/* ---------- state / render ---------- */

async function refreshState() {
  try {
    const s = demo ? demoState() : await api("get_state");
    if (!s) return;
    state = s;
    trackRuntimeTransitions(s);
    renderAll();
    checkUsageLimits();
  } catch (e) {
    console.error(e);
  }
}

function renderAll() {
  if (!state) return;
  if (state.proxy_recovery && state.proxy_recovery !== lastProxyRecovery) {
    lastProxyRecovery = state.proxy_recovery;
    const recovery = state.proxy_recovery;
    if (recovery.error) toast(recovery.error, "error");
    else if (recovery.restored) toast("偵測到上次未清理的系統代理，已自動恢復原始設定。", "ok");
    else if (recovery.cleared_stale) toast("已清除過期的代理快照；目前系統代理未被覆蓋。", "ok");
  }  $("#foot-dot").className = "dot" + (state.running ? " on" : "");
  $("#foot-core").textContent = state.running ? "核心運行中" : "核心未啟動";
  $("#foot-proxy").textContent = "系統代理：" + (state.sys_proxy ? "開" : "關");
  $("#app-version").textContent = "v" + state.app_version;

  $("#st-dot").className = "dot big" + (state.running ? " on" : "");
  $("#st-text").textContent = state.running ? "核心運行中" : state.core_found ? "核心已停止" : "找不到 mihomo 核心";
  $("#st-version").textContent = state.core_version ? "mihomo " + state.core_version : "mihomo 未啟動";

  const btn = $("#btn-toggle-core");
  btn.textContent = state.running ? "停止核心" : "啟動 KumoRoute";
  btn.classList.toggle("primary", !state.running);

  $("#sw-sysproxy").checked = !!state.sys_proxy;
  $$("#mode-seg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === state.mode));

  const ap = state.active_profile;
  $("#cur-profile").textContent = ap ? ap.name : "—";
  $("#cur-profile-kind").textContent = !ap ? "" :
    ap.kind === "remote" ? "遠端訂閱 · 更新於 " + ap.updated_at :
    ap.kind === "builtin" ? "內建配置" : "本機 YAML · " + ap.updated_at;
  $("#cur-profile-tip").textContent = ap && ap.kind === "builtin"
    ? "目前是內建直連配置，流量不經任何代理。到「訂閱」新增你的 Clash 訂閱連結。"
    : "";
  $("#btn-update-profile").disabled = !(ap && ap.kind === "remote");

  $("#test-url-label").textContent = state.test_url || "";

  $("#about-appver").textContent = "v" + state.app_version;
  $("#about-corever").textContent = state.core_version || "—";
  $("#about-datadir").textContent = state.data_dir || "—";
  if (document.activeElement !== $("#in-mixed-port")) $("#in-mixed-port").value = state.mixed_port;
  if (document.activeElement !== $("#in-ctl-port")) $("#in-ctl-port").value = state.controller_port;

  renderProfiles();
  if (!state.running) { setSpeeds(0, 0, 0); }
}

function renderProfiles() {
  const box = $("#profile-list");
  if (!state || !state.profiles.length) {
    box.innerHTML = '<div class="empty">尚無配置</div>';
    return;
  }
  box.innerHTML = state.profiles.map((p) => {
    const active = state.active_profile && p.id === state.active_profile.id;
    const kind = p.kind === "remote" ? "遠端訂閱" : p.kind === "builtin" ? "內建" : "本機 YAML";
    const isPending = pendingDelete.id === p.id;
    return `
    <div class="profile-row${active ? " active" : ""}" data-id="${esc(p.id)}">
      <div class="profile-info">
        <div class="name">${esc(p.name)} ${active ? '<span class="badge-active">使用中</span>' : ""}</div>
        <div class="meta">${kind} · ${esc(p.updated_at || "")}</div>
      </div>
      <div class="profile-actions">
        ${active ? "" : `<button class="btn ghost small" data-act="activate">啟用</button>`}
        ${p.kind === "remote" ? `<button class="btn ghost small" data-act="update">更新</button>` : ""}
        ${p.kind !== "builtin" ? `<button class="btn ghost small ${isPending ? "danger" : ""}" data-act="delete">${isPending ? "確認刪除？" : "刪除"}</button>` : ""}
      </div>
    </div>`;
  }).join("");
}

/* ---------- live traffic ---------- */

function setSpeeds(down, up, count) {
  $("#sp-down").textContent = fmtBytes(down, true);
  $("#sp-up").textContent = fmtBytes(up, true);
  $("#sp-count").textContent = String(count);
  sparkDown.push(down); sparkUp.push(up);
  if (sparkDown.length > 60) sparkDown.shift();
  if (sparkUp.length > 60) sparkUp.shift();
  drawSpark();
}

async function tickLive() {
  if (!state) return;
  if (!state.running) {
    prevTotals = null;
    setSpeeds(0, 0, 0);
    if (page === "stats") renderStatsPage();
    return;
  }
  try {
    const live = demo ? demoLive() : await api("get_live");
    if (!live || !live.running) {
      prevTotals = null;
      setSpeeds(0, 0, 0);
      if (page === "stats") renderStatsPage();
      return;
    }
    const now = performance.now() / 1000;
    const count = Number(live.count) || 0;
    peakConnections = Math.max(peakConnections, count);
    if (prevTotals && now - prevTotals.t > 0.2) {
      const dt = now - prevTotals.t;
      const downDelta = Math.max(0, live.down_total - prevTotals.down);
      const upDelta = Math.max(0, live.up_total - prevTotals.up);
      const down = downDelta / dt;
      const up = upDelta / dt;
      peakDownSpeed = Math.max(peakDownSpeed, down);
      peakUpSpeed = Math.max(peakUpSpeed, up);
      addUsage(downDelta, upDelta);
      setSpeeds(down, up, count);
      if (downDelta || upDelta) checkUsageLimits();
    }
    recordConnections(live.connections || []);
    prevTotals = { t: now, down: live.down_total, up: live.up_total };
    $("#sp-down-total").textContent = fmtBytes(live.down_total);
    $("#sp-up-total").textContent = fmtBytes(live.up_total);
    if (statsDirty && Date.now() - lastStatsSave > 5000) saveUsageData();
    if (page === "stats") renderStatsPage();
  } catch (e) { /* ignore */ }
}

function drawSpark() {
  const cv = $("#spark");
  if (!cv) return;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const all = sparkDown.concat(sparkUp);
  const max = Math.max(1024, ...all) * 1.15;
  const n = Math.max(sparkDown.length, 2);
  const stepX = w / Math.max(59, n - 1);
  const toXY = (arr, i) => [i * stepX, h - (arr[i] / max) * (h - 6) - 3];

  const drawLine = (arr, color) => {
    if (!arr.length) return;
    ctx.beginPath();
    arr.forEach((_, i) => {
      const [x, y] = toXY(arr, i);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.lineJoin = "round";
    ctx.stroke();
  };

  if (sparkDown.length > 1) {
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "rgba(110,168,255,0.28)");
    grad.addColorStop(1, "rgba(110,168,255,0)");
    ctx.beginPath();
    sparkDown.forEach((_, i) => {
      const [x, y] = toXY(sparkDown, i);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo((sparkDown.length - 1) * stepX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
  }
  drawLine(sparkDown, "#6ea8ff");
  drawLine(sparkUp, "rgba(61,220,151,0.9)");
}

function recordDelayHistory(groupName, delays) {
  if (!groupName || !delays || typeof delays !== "object") return;
  const now = new Date().toISOString();
  const bucket = usageData.nodeHealth[groupName] || {};
  Object.entries(delays).forEach(([nodeName, value]) => {
    const ms = Number(value) > 0 ? Number(value) : null;
    const history = Array.isArray(bucket[nodeName]) ? bucket[nodeName] : [];
    history.push({ t: now, ms });
    if (history.length > 10) history.splice(0, history.length - 10);
    bucket[nodeName] = history;
  });
  usageData.nodeHealth[groupName] = bucket;
  statsDirty = true;
  saveUsageData(true);
}

function healthSummary(samples) {
  const recent = samples.slice(-10);
  const successes = recent.map((s) => s.ms).filter((v) => typeof v === "number" && v > 0);
  const tests = recent.length;
  const avg = successes.length ? successes.reduce((a, b) => a + b, 0) / successes.length : null;
  const timeoutRate = tests ? 1 - successes.length / tests : 1;
  let stability = 0;
  if (successes.length && avg) {
    const variance = successes.reduce((sum, v) => sum + (v - avg) ** 2, 0) / successes.length;
    stability = Math.max(0, Math.min(100, Math.round(100 - (Math.sqrt(variance) / Math.max(avg, 1)) * 100)));
  }
  const score = (1 - timeoutRate) * 10000 - (avg || 5000) - (100 - stability) * 2;
  const grade = timeoutRate > 0.4 || (avg || 9999) > 500 ? "bad" : timeoutRate > 0.15 || (avg || 9999) > 250 || stability < 55 ? "mid" : "good";
  return { tests, successes: successes.length, avg, timeoutRate, stability, score, grade, recent };
}

function healthDotClass(ms) {
  if (ms === null || ms === undefined || ms <= 0) return "bad";
  if (ms <= 200) return "good";
  if (ms <= 500) return "mid";
  return "bad";
}

function renderNodeHealth() {
  const box = $("#node-health");
  if (!box) return;
  const groupNames = Array.from(new Set([
    ...groups.map((g) => g.name),
    ...Object.keys(usageData.nodeHealth || {}),
  ]));
  let rendered = 0;
  const html = groupNames.map((groupName, groupIndex) => {
    const bucket = usageData.nodeHealth[groupName] || {};
    const entries = Object.entries(bucket)
      .map(([name, samples]) => ({ name, samples, summary: healthSummary(samples) }))
      .filter((entry) => entry.samples.length > 0)
      .sort((a, b) => b.summary.score - a.summary.score);
    if (!entries.length) return "";
    rendered += 1;
    const best = entries.find((entry) => entry.summary.tests >= 2 && entry.summary.successes > 0);
    const rows = entries.map((entry) => {
      const s = entry.summary;
      const avg = s.avg === null ? "—" : `${Math.round(s.avg)} ms`;
      const timeout = `${Math.round(s.timeoutRate * 100)}% 逾時`;
      const dots = s.recent.map((sample) => {
        const label = sample.ms ? `${sample.ms} ms` : "逾時";
        return `<span class="health-dot ${healthDotClass(sample.ms)}" title="${esc(sample.t)} · ${label}"></span>`;
      }).join("");
      return `
        <div class="health-row">
          <div class="health-node" title="${esc(entry.name)}">${esc(entry.name)}</div>
          <div class="health-history">${dots}</div>
          <div class="health-stat">${avg} · ${timeout} · 穩定 ${s.stability}</div>
          <span class="health-grade ${s.grade}">${s.grade === "good" ? "穩定" : s.grade === "mid" ? "普通" : "不穩"}</span>
        </div>`;
    }).join("");
    const bestHtml = best
      ? `<span class="health-best">推薦：${esc(best.name)} · ${Math.round(best.summary.avg)} ms</span>
         <button class="btn ghost small health-use" data-use-node="1" data-group="${esc(groupName)}" data-node="${esc(best.name)}">套用</button>`
      : '<span class="health-best muted">再測速幾次即可推薦</span>';
    return `
      <details class="health-group" ${groupIndex === 0 ? "open" : ""}>
        <summary>
          <span class="health-group-name">${esc(groupName)}</span>
          ${bestHtml}
        </summary>
        <div class="health-list">${rows}</div>
      </details>`;
  }).join("");
  box.innerHTML = rendered
    ? html
    : '<div class="attr-empty">尚無節點測速紀錄。到「代理」頁按一次「測速」後，這裡會開始累積最近 10 次結果。</div>';
}

function safeAttrKey(key) {
  const value = String(key || "").trim();
  if (!value || value === "__proto__" || value === "constructor" || value === "prototype") return "";
  return value.slice(0, 180);
}

function pruneAttrBucket(bucket) {
  const keys = Object.keys(bucket);
  if (keys.length <= 150) return;
  keys
    .sort((a, b) => {
      const ea = bucket[a] || {};
      const eb = bucket[b] || {};
      return (Number(eb.down || 0) + Number(eb.up || 0) + Number(eb.count || 0)) -
             (Number(ea.down || 0) + Number(ea.up || 0) + Number(ea.count || 0));
    })
    .slice(150)
    .forEach((key) => delete bucket[key]);
}

function bumpAttr(bucket, key, down, up, count = 0) {
  key = safeAttrKey(key);
  if (!key) return;
  const item = bucket[key] || { down: 0, up: 0, count: 0 };
  item.down += Math.max(0, Number(down) || 0);
  item.up += Math.max(0, Number(up) || 0);
  item.count += Math.max(0, Number(count) || 0);
  bucket[key] = item;
  pruneAttrBucket(bucket);
}

function cleanHost(value) {
  let host = String(value || "").trim().toLowerCase();
  if (!host) return "";
  try {
    if (/^https?:\/\//.test(host)) host = new URL(host).hostname;
  } catch (e) { /* ignore */ }
  host = host.replace(/^\[|\]$/g, "").replace(/:\d+$/, "").replace(/\.$/, "");
  return host.slice(0, 180);
}

function uniqueChains(chains) {
  return Array.from(new Set((Array.isArray(chains) ? chains : []).map((x) => String(x || "").trim()).filter(Boolean)));
}

function recordConnections(connections) {
  if (!Array.isArray(connections) || !connections.length) {
    connectionSnapshots = new Map();
    return;
  }
  const next = new Map();
  const profile = state && state.active_profile ? state.active_profile.name : "未指定配置";
  connections.slice(0, 2000).forEach((conn) => {
    const id = String(conn.id || "");
    if (!id) return;
    const down = Math.max(0, Number(conn.download) || 0);
    const up = Math.max(0, Number(conn.upload) || 0);
    const prev = connectionSnapshots.get(id);
    const downDelta = prev ? Math.max(0, down - prev.down) : down;
    const upDelta = prev ? Math.max(0, up - prev.up) : up;
    const isNew = !prev;

    if (downDelta || upDelta) {
      bumpAttr(usageData.attribution.profiles, profile, downDelta, upDelta);
      const chains = uniqueChains(conn.chains);
      chains.forEach((chainName) => {
        if (knownGroupNames.has(chainName)) {
          bumpAttr(usageData.attribution.groups, chainName, downDelta, upDelta);
        } else {
          bumpAttr(usageData.attribution.nodes, chainName, downDelta, upDelta);
        }
      });
      if (usageData.domainTracking) {
        const host = cleanHost(conn.host);
        if (host) bumpAttr(usageData.attribution.domains, host, downDelta, upDelta);
      }
      statsDirty = true;
    }

    if (isNew && usageData.domainTracking) {
      const rule = safeAttrKey(conn.rule);
      if (rule) {
        const payload = safeAttrKey(conn.rulePayload);
        const label = payload ? `${rule}(${payload})` : rule;
        bumpAttr(usageData.attribution.rules, label, 0, 0, 1);
      }
    }
    next.set(id, { down, up });
  });
  connectionSnapshots = next;
}

function topAttrEntries(bucket, limit = 5) {
  return Object.entries(bucket || {})
    .map(([name, value]) => ({ name, ...value }))
    .sort((a, b) => (Number(b.down || 0) + Number(b.up || 0) + Number(b.count || 0)) - (Number(a.down || 0) + Number(a.up || 0) + Number(a.count || 0)))
    .slice(0, limit);
}

function renderAttrList(selector, bucket, mode = "bytes", disabled = false) {
  const box = $(selector);
  if (!box) return;
  if (disabled) {
    box.innerHTML = '<div class="attr-empty">未啟用</div>';
    return;
  }
  const rows = topAttrEntries(bucket);
  if (!rows.length) {
    box.innerHTML = '<div class="attr-empty">尚無資料</div>';
    return;
  }
  box.innerHTML = rows.map((row) => `
    <div class="attr-row">
      <span class="attr-name" title="${esc(row.name)}">${esc(row.name)}</span>
      <span class="attr-val">${mode === "count" ? `${Number(row.count || 0)} 次` : fmtBytes(Number(row.down || 0) + Number(row.up || 0))}</span>
    </div>`).join("");
}

function renderAttribution() {
  const attr = usageData.attribution || emptyAttribution();
  renderAttrList("#attr-profiles", attr.profiles);
  renderAttrList("#attr-groups", attr.groups);
  renderAttrList("#attr-nodes", attr.nodes);
  renderAttrList("#attr-domains", attr.domains, "bytes", !usageData.domainTracking);
  renderAttrList("#attr-rules", attr.rules, "count", !usageData.domainTracking);
}

function statsExportSnapshot() {
  flushSystemProxyUptime();
  const data = JSON.parse(JSON.stringify(usageData));
  data.systemProxySeconds = Math.round(currentSystemProxySeconds() * 1000) / 1000;
  return {
    product: "KumoRoute",
    appVersion: state ? state.app_version : "",
    exportedAt: new Date().toISOString(),
    sessionSeconds: Math.round((Date.now() - sessionStartedAt) / 1000),
    data,
  };
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function statsCsv(snapshot) {
  const lines = [];
  const section = (title) => { lines.push("", "# " + title); };
  const row = (values) => lines.push(values.map(csvCell).join(","));

  section("DAILY_USAGE");
  row(["date", "download_bytes", "upload_bytes"]);
  Object.entries(snapshot.data.days).sort().forEach(([date, value]) => row([date, value.down || 0, value.up || 0]));

  section("NODE_HEALTH");
  row(["group", "node", "tests", "successes", "avg_latency_ms", "timeout_rate", "stability"]);
  Object.entries(snapshot.data.nodeHealth).forEach(([group, nodes]) => {
    Object.entries(nodes).forEach(([node, samples]) => {
      const s = healthSummary(samples);
      row([group, node, s.tests, s.successes, s.avg === null ? "" : Math.round(s.avg), Math.round(s.timeoutRate * 100) + "%", s.stability]);
    });
  });

  section("ATTRIBUTION");
  row(["category", "name", "download_bytes", "upload_bytes", "count"]);
  Object.entries(snapshot.data.attribution).forEach(([category, bucket]) => {
    Object.entries(bucket || {}).forEach(([name, value]) => row([category, name, value.down || 0, value.up || 0, value.count || 0]));
  });

  section("EVENTS");
  row(["timestamp", "type", "title", "detail"]);
  snapshot.data.events.forEach((event) => row([event.t, event.type, event.title, event.detail]));

  section("CORE");
  row(["metric", "value"]);
  row(["starts", snapshot.data.core.starts]);
  row(["restarts", snapshot.data.core.restarts]);
  row(["last_started_at", snapshot.data.core.lastStartedAt || ""]);
  row(["system_proxy_seconds", snapshot.data.systemProxySeconds]);
  return lines.join("\n");
}

function demoDownload(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportStats(format) {
  const snapshot = statsExportSnapshot();
  const isCsv = format === "csv";
  const content = isCsv ? statsCsv(snapshot) : JSON.stringify(snapshot, null, 2);
  const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
  const filename = `KumoRoute-stats-${stamp}.${format}`;
  if (demo) {
    demoDownload(filename, content, isCsv ? "text/csv;charset=utf-8" : "application/json;charset=utf-8");
    toast(`已匯出 ${filename}`, "ok");
    return;
  }
  try {
    const res = await api("save_stats_export", format, content);
    if (res && res.ok) toast(`統計已匯出：${res.path}`, "ok");
    else toast((res && res.error) || "匯出失敗", "error");
  } catch (e) {
    toast(String(e), "error");
  }
}

function clearStatsData() {
  const limits = { ...usageData.limits, notifiedDay: "", notifiedWeek: "" };
  const domainTracking = usageData.domainTracking;
  usageData = defaultUsageData();
  usageData.limits = limits;
  usageData.domainTracking = domainTracking;
  connectionSnapshots = new Map();
  peakConnections = 0;
  peakDownSpeed = 0;
  peakUpSpeed = 0;
  sessionStartedAt = Date.now();
  statsDirty = true;
  saveUsageData(true);
  checkUsageLimits();
  renderStatsPage();
  toast("本機統計已清除", "ok");
}

function seedDemoStats() {
  const samples = [
    [180 * 1048576, 9 * 1048576],
    [245 * 1048576, 12 * 1048576],
    [120 * 1048576, 7 * 1048576],
    [430 * 1048576, 19 * 1048576],
    [280 * 1048576, 14 * 1048576],
    [610 * 1048576, 27 * 1048576],
    [365 * 1048576, 18 * 1048576],
  ];
  samples.forEach(([down, up], index) => {
    const d = new Date();
    d.setDate(d.getDate() - (samples.length - 1 - index));
    usageData.days[localDayKey(d)] = { down, up };
  });

  const now = Date.now();
  const mkHistory = (values) => values.map((ms, index) => ({
    t: new Date(now - (values.length - 1 - index) * 90000).toISOString(),
    ms: ms > 0 ? ms : null,
  }));
  usageData.nodeHealth = {
    PROXY: {
      "香港 01": mkHistory([96, 88, 102, 91, 110, 95, 87, 99]),
      "香港 02": mkHistory([188, 201, 176, 192, 210, 0, 185]),
      "日本 02": mkHistory([72, 68, 81, 76, 70, 74, 79, 73, 71]),
      "新加坡 04": mkHistory([98, 112, 105, 101, 108, 99, 103]),
      "香港 05": mkHistory([104, 118, 121, 0, 109]),
    },
    "自動選擇": {
      "日本 02": mkHistory([71, 78, 74, 69, 73, 76]),
      "香港 01": mkHistory([93, 101, 97, 95, 99, 92]),
      "新加坡 04": mkHistory([100, 109, 105, 112, 107, 104]),
    },
  };
  usageData.attribution = {
    profiles: { "範例機場": { down: 2415919104, up: 120586240, count: 0 } },
    groups: {
      PROXY: { down: 1900000000, up: 93000000, count: 0 },
      "自動選擇": { down: 1500000000, up: 74000000, count: 0 },
      "串流媒體": { down: 515919104, up: 27586240, count: 0 },
    },
    nodes: {
      "日本 02": { down: 928000000, up: 44200000, count: 0 },
      "香港 01": { down: 732000000, up: 35100000, count: 0 },
      "新加坡 04": { down: 611000000, up: 30200000, count: 0 },
    },
    domains: {
      "youtube.com": { down: 844000000, up: 32000000, count: 0 },
      "github.com": { down: 311000000, up: 12400000, count: 0 },
      "openai.com": { down: 266000000, up: 18800000, count: 0 },
      "google.com": { down: 152000000, up: 7600000, count: 0 },
    },
    rules: {
      "DomainSuffix(youtube.com)": { down: 0, up: 0, count: 128 },
      "DomainKeyword(github)": { down: 0, up: 0, count: 74 },
      "DomainSuffix(openai.com)": { down: 0, up: 0, count: 41 },
      "MATCH": { down: 0, up: 0, count: 219 },
    },
  };
  usageData.core = { starts: 18, restarts: 2, lastStartedAt: new Date(now - 42 * 60000).toISOString() };
  usageData.systemProxySeconds = 2 * 3600 + 17 * 60;
  usageData.limits = { daily: 10 * 1073741824, weekly: 50 * 1073741824, notifiedDay: "", notifiedWeek: "" };
  usageData.domainTracking = true;
  usageData.events = [
    { t: new Date(now - 42 * 60000).toISOString(), type: "core", title: "核心已啟動", detail: "mihomo v1.19.33" },
    { t: new Date(now - 36 * 60000).toISOString(), type: "proxy", title: "系統代理已開啟", detail: "" },
    { t: new Date(now - 21 * 60000).toISOString(), type: "subscription", title: "訂閱已更新", detail: "範例機場" },
    { t: new Date(now - 8 * 60000).toISOString(), type: "profile", title: "已套用推薦節點", detail: "PROXY → 日本 02" },
  ];
  saveUsageData(true);
}

function formatEventTime(value) {
  try {
    return new Date(value).toLocaleString("zh-TW", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "";
  }
}

function eventTypeName(type) {
  return ({ core: "核心", proxy: "代理", subscription: "訂閱", limit: "上限", profile: "配置" })[type] || "事件";
}

function renderEventList() {
  const box = $("#event-list");
  if (!box) return;
  const events = usageData.events.slice(-8).reverse();
  box.innerHTML = events.length
    ? events.map((event) => `
      <div class="event-row">
        <span class="event-type ${esc(event.type)}">${esc(eventTypeName(event.type))}</span>
        <span class="event-title" title="${esc(event.detail || "")}">${esc(event.title)}${event.detail ? " · " + esc(event.detail) : ""}</span>
        <span class="event-time">${esc(formatEventTime(event.t))}</span>
      </div>`).join("")
    : '<div class="attr-empty">尚無事件紀錄</div>';
}

function renderStatsPage() {
  if (!$("#stats-today-total")) return;
  const days = recentDays(30);
  const today = days[days.length - 1] || { down: 0, up: 0 };
  const totalDown = days.reduce((sum, d) => sum + d.down, 0);
  const totalUp = days.reduce((sum, d) => sum + d.up, 0);
  $("#stats-today-total").textContent = fmtBytes(today.down + today.up);
  $("#stats-today-down").textContent = fmtBytes(today.down);
  $("#stats-today-up").textContent = fmtBytes(today.up);
  $("#stats-session-time").textContent = fmtDuration((Date.now() - sessionStartedAt) / 1000);
  $("#stats-peak-conn").textContent = String(peakConnections);
  $("#stats-peak-speed").textContent = fmtBytes(peakDownSpeed, true);
  $("#stats-peak-speed-sub").textContent = `上傳峰值 ${fmtBytes(peakUpSpeed, true)}`;
  $("#stats-total-down").textContent = fmtBytes(totalDown);
  $("#stats-total-up").textContent = fmtBytes(totalUp);
  $("#stats-total-sum").textContent = fmtBytes(totalDown + totalUp);
  $("#core-starts").textContent = `${usageData.core.starts || 0} 次`;
  $("#core-restarts").textContent = `${usageData.core.restarts || 0} 次`;
  $("#core-last-start").textContent = usageData.core.lastStartedAt ? formatEventTime(usageData.core.lastStartedAt) : "—";
  $("#proxy-uptime").textContent = fmtDuration(currentSystemProxySeconds());
  if (document.activeElement !== $("#limit-daily")) {
    $("#limit-daily").value = usageData.limits.daily > 0 ? (usageData.limits.daily / 1073741824).toFixed(2) : "0";
  }
  if (document.activeElement !== $("#limit-weekly")) {
    $("#limit-weekly").value = usageData.limits.weekly > 0 ? (usageData.limits.weekly / 1073741824).toFixed(2) : "0";
  }
  $("#sw-domain-tracking").checked = !!usageData.domainTracking;
  renderEventList();
  renderNodeHealth();
  renderAttribution();
  drawStatsChart();
}

function drawStatsChart() {
  const cv = $("#stats-chart");
  if (!cv) return;
  const w = cv.clientWidth;
  const h = cv.clientHeight || 180;
  if (!w) return;
  const dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const series = recentDays(7);
  const totals = series.map((d) => d.down + d.up);
  const max = Math.max(1, ...totals);
  const left = 8;
  const right = 8;
  const top = 20;
  const bottom = 27;
  const plotW = Math.max(1, w - left - right);
  const plotH = Math.max(1, h - top - bottom);
  const baseline = top + plotH;
  const slot = plotW / series.length;

  ctx.strokeStyle = "rgba(255,255,255,0.055)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = top + (plotH * i) / 3;
    ctx.beginPath();
    ctx.moveTo(left, y + 0.5);
    ctx.lineTo(w - right, y + 0.5);
    ctx.stroke();
  }

  series.forEach((day, i) => {
    const total = day.down + day.up;
    const totalH = total ? Math.max(3, (total / max) * plotH) : 0;
    const downH = total ? (day.down / total) * totalH : 0;
    const upH = total ? (day.up / total) * totalH : 0;
    const barW = Math.min(32, slot * 0.54);
    const x = left + i * slot + (slot - barW) / 2;
    const upY = baseline - totalH;
    const downY = upY + upH;

    if (downH > 0) {
      ctx.fillStyle = "rgba(110,168,255,0.9)";
      ctx.fillRect(x, downY, barW, downH);
    }
    if (upH > 0) {
      ctx.fillStyle = "rgba(61,220,151,0.88)";
      ctx.fillRect(x, upY, barW, upH);
    }

    ctx.fillStyle = "rgba(139,149,167,0.95)";
    ctx.font = "11px 'Microsoft JhengHei UI', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`${day.date.getMonth() + 1}/${day.date.getDate()}`, x + barW / 2, h - 9);
    ctx.fillStyle = "rgba(232,237,246,0.8)";
    ctx.font = "10px 'Microsoft JhengHei UI', sans-serif";
    if (total > 0) ctx.fillText(fmtBytes(total), x + barW / 2, Math.max(11, upY - 5));
  });
}

/* ---------- proxies ---------- */

async function refreshGroups() {
  try {
    if (!state || !state.running) { groups = []; renderGroups(); return; }
    const res = demo ? await demoApi("get_proxy_groups") : await api("get_proxy_groups");
    groups = (res && res.groups) || [];
    knownGroupNames = new Set(groups.map((g) => g.name));
    renderGroups();
    if (page === "stats") renderNodeHealth();
  } catch (e) {
    console.error(e);
  }
}

function delayBadge(groupName, node) {
  const d = (groupDelays[groupName] || {})[node.name];
  if (d === undefined || d === null) return '<span class="delay none">—</span>';
  if (!d) return '<span class="delay bad">逾時</span>';
  const cls = d <= 200 ? "good" : d <= 500 ? "mid" : "bad";
  return `<span class="delay ${cls}">${d} ms</span>`;
}

function renderGroups() {
  const box = $("#groups");
  const empty = $("#proxies-empty");
  if (!groups.length) {
    box.innerHTML = "";
    empty.classList.remove("hidden");
    empty.textContent = state && state.running ? "此配置中沒有策略組（proxy-groups）。" : "核心未啟動。";
    return;
  }
  empty.classList.add("hidden");
  box.innerHTML = groups.map((g, gi) => `
    <div class="card group-card">
      <div class="group-head">
        <span class="group-name">${esc(g.name)}</span>
        <span class="pill">${esc(g.type)}</span>
        <span class="pill">當前：${esc(g.now || "—")}</span>
        <button class="btn ghost small" data-test="${gi}">測速</button>
      </div>
      <div class="node-list">
        ${(g.nodes || []).map((n) => `
          <div class="node${n.name === g.now ? " active" : ""}" data-group="${esc(g.name)}" data-node="${esc(n.name)}">
            <span class="node-name">${esc(n.name)}</span>
            <span class="node-type">${esc(n.type)}</span>
            ${delayBadge(g.name, n)}
          </div>`).join("")}
      </div>
    </div>`).join("");
}

/* ---------- logs ---------- */

async function refreshLogs() {
  try {
    const res = demo ? await demoApi("get_logs") : await api("get_logs");
    const lines = (res && res.lines) || [];
    const box = $("#logbox");
    box.innerHTML = lines.length
      ? lines.map((ln) => `<span class="${/error|fail/i.test(ln) ? "log-error" : /warn/i.test(ln) ? "log-warn" : ""}">${esc(ln)}</span>`).join("\n")
      : "（尚無日誌）";
    if ($("#log-autoscroll").checked) box.scrollTop = box.scrollHeight;
  } catch (e) { /* ignore */ }
}

/* ---------- page nav ---------- */

function switchPage(name) {
  page = name;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + name));
  if (name === "proxies") refreshGroups();
  if (name === "logs") refreshLogs();
  if (name === "settings") renderAll();
  if (name === "stats") {
    if (state && state.running) refreshGroups();
    renderStatsPage();
    tickLive();
    checkUsageLimits();
  }
}

function bindNav() {
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => switchPage(b.dataset.page)));
}

/* ---------- actions ---------- */

function bindActions() {
  $("#btn-toggle-core").addEventListener("click", async () => {
    const btn = $("#btn-toggle-core");
    btn.disabled = true;
    try {
      const res = state && state.running ? await api("stop_core") : await api("start_core");
      if (res && res.ok === false) toast(res.error || "操作失敗", "error");
      prevTotals = null;
      sparkDown = []; sparkUp = [];
      await refreshState();
      if (page === "proxies") await refreshGroups();
    } catch (e) { toast(String(e), "error"); }
    btn.disabled = false;
  });

  $("#sw-sysproxy").addEventListener("change", async (ev) => {
    const on = ev.target.checked;
    ev.target.disabled = true;
    try {
      const res = await api("set_system_proxy", on);
      if (res && res.ok === false) toast(res.error || "系統代理設定失敗", "error");
      else toast(on ? "系統代理已開啟" : "系統代理已關閉", "ok");
      await refreshState();
    } catch (e) { toast(String(e), "error"); }
    ev.target.disabled = false;
  });

  $("#mode-seg").addEventListener("click", async (ev) => {
    const b = ev.target.closest("button[data-mode]");
    if (!b) return;
    const res = await api("set_mode", b.dataset.mode);
    if (res && res.ok === false) toast(res.error || "切換失敗", "error");
    await refreshState();
  });

  $("#btn-update-profile").addEventListener("click", async () => {
    if (!state || !state.active_profile) return;
    const btn = $("#btn-update-profile");
    btn.disabled = true; btn.textContent = "更新中…";
    try {
      const res = await api("update_profile", state.active_profile.id);
      if (res && res.ok === false) toast(res.error || "更新失敗", "error");
      else {
        addEvent("subscription", "訂閱已更新", state && state.active_profile ? state.active_profile.name : "");
        toast("訂閱已更新", "ok");
      }
      await refreshState();
    } catch (e) { toast(String(e), "error"); }
    btn.textContent = "更新訂閱";
  });

  $("#groups").addEventListener("click", async (ev) => {
    const t = ev.target.closest("button[data-test]");
    if (t) {
      const g = groups[Number(t.dataset.test)];
      if (!g) return;
      t.disabled = true; t.textContent = "測速中…";
      try {
        const res = demo ? await demoApi("test_group_delay", g.name) : await api("test_group_delay", g.name);
        if (res && res.ok) {
          groupDelays[g.name] = res.delays || {};
          recordDelayHistory(g.name, res.delays || {});
          renderGroups();
          if (page === "stats") renderNodeHealth();
          toast("測速完成", "ok");
        } else toast((res && res.error) || "測速失敗", "error");
      } catch (e) { toast(String(e), "error"); }
      return;
    }
    const n = ev.target.closest(".node");
    if (n) {
      const res = demo ? await demoApi("select_proxy", n.dataset.group, n.dataset.node) : await api("select_proxy", n.dataset.group, n.dataset.node);
      if (res && res.ok === false) toast(res.error || "切換失敗", "error");
      await refreshGroups();
    }
  });

  $("#sub-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = $("#sub-url").value.trim();
    const name = $("#sub-name").value.trim();
    const err = $("#sub-error");
    err.classList.add("hidden");
    if (!/^https?:\/\//i.test(url)) {
      err.textContent = "請輸入 http(s):// 開頭的訂閱連結";
      err.classList.remove("hidden");
      return;
    }
    const btn = $("#btn-add-sub");
    btn.disabled = true; btn.textContent = "新增中…";
    try {
      const res = await api("add_subscription", url, name);
      if (res && res.ok === false) {
        err.textContent = res.error || "新增失敗";
        err.classList.remove("hidden");
      } else {
        $("#sub-url").value = ""; $("#sub-name").value = "";
        addEvent("subscription", "訂閱已新增", name || "遠端訂閱");
        toast("訂閱已新增並啟用", "ok");
        await refreshState();
        await refreshGroups();
      }
    } catch (e) { err.textContent = String(e); err.classList.remove("hidden"); }
    btn.disabled = false; btn.textContent = "新增";
  });

  $("#btn-import-file").addEventListener("click", async () => {
    try {
      const res = await api("import_profile");
      if (res && res.ok) {
        addEvent("subscription", "本機配置已匯入", "");
        toast("配置已匯入並啟用", "ok");
        await refreshState();
        await refreshGroups();
      } else if (res && res.error) toast(res.error, "error");
    } catch (e) { toast(String(e), "error"); }
  });

  $("#profile-list").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const row = btn.closest(".profile-row");
    const id = row && row.dataset.id;
    if (!id) return;
    const act = btn.dataset.act;

    if (act === "activate") {
      btn.disabled = true;
      const res = await api("set_active_profile", id);
      if (res && res.ok === false) toast(res.error || "啟用失敗", "error");
      else {
        addEvent("subscription", "已切換配置", row.querySelector(".name")?.textContent?.trim() || "");
        toast("已切換配置", "ok");
      }
      await refreshState();
      if (page === "proxies") await refreshGroups();
    } else if (act === "update") {
      btn.disabled = true; btn.textContent = "更新中…";
      const res = await api("update_profile", id);
      if (res && res.ok === false) toast(res.error || "更新失敗", "error");
      else {
        addEvent("subscription", "訂閱已更新", row.querySelector(".name")?.textContent?.trim() || "");
        toast("訂閱已更新", "ok");
      }
      await refreshState();
    } else if (act === "delete") {
      if (pendingDelete.id !== id) {
        clearTimeout(pendingDelete.timer);
        pendingDelete = { id, timer: setTimeout(() => { pendingDelete = { id: null, timer: null }; renderProfiles(); }, 2600) };
        renderProfiles();
        return;
      }
      clearTimeout(pendingDelete.timer);
      pendingDelete = { id: null, timer: null };
      const res = await api("delete_profile", id);
      if (res && res.ok === false) toast(res.error || "刪除失敗", "error");
      else {
        addEvent("subscription", "配置已刪除", row.querySelector(".name")?.textContent?.trim() || "");
        toast("已刪除", "ok");
      }
      await refreshState();
      if (page === "proxies") await refreshGroups();
    }
  });

  $("#node-health").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-use-node]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    btn.disabled = true;
    try {
      const res = await api("select_proxy", btn.dataset.group, btn.dataset.node);
      if (res && res.ok === false) toast(res.error || "切換失敗", "error");
      else {
        addEvent("profile", "已套用推薦節點", `${btn.dataset.group} → ${btn.dataset.node}`);
        toast(`已套用：${btn.dataset.node}`, "ok");
      }
      await refreshState();
      await refreshGroups();
      renderNodeHealth();
    } catch (e) { toast(String(e), "error"); }
    btn.disabled = false;
  });

  $("#btn-save-limits").addEventListener("click", () => {
    const gb = 1073741824;
    usageData.limits.daily = Math.max(0, Number($("#limit-daily").value) || 0) * gb;
    usageData.limits.weekly = Math.max(0, Number($("#limit-weekly").value) || 0) * gb;
    usageData.limits.notifiedDay = "";
    usageData.limits.notifiedWeek = "";
    usageData.domainTracking = $("#sw-domain-tracking").checked;
    statsDirty = true;
    if (usageData.limits.daily > 0 || usageData.limits.weekly > 0) maybeRequestNotifications();
    saveUsageData(true);
    checkUsageLimits();
    renderStatsPage();
    toast("統計設定已保存", "ok");
  });

  $("#btn-export-csv").addEventListener("click", () => exportStats("csv"));
  $("#btn-export-json").addEventListener("click", () => exportStats("json"));
  $("#btn-clear-stats").addEventListener("click", () => {
    const btn = $("#btn-clear-stats");
    if (!clearStatsPending) {
      clearStatsPending = true;
      btn.textContent = "再次點擊確認清除";
      clearTimeout(clearStatsTimer);
      clearStatsTimer = setTimeout(() => { clearStatsPending = false; btn.textContent = "清除統計"; }, 3200);
      return;
    }
    clearTimeout(clearStatsTimer);
    clearStatsPending = false;
    btn.textContent = "清除統計";
    clearStatsData();
  });

  $("#btn-save-ports").addEventListener("click", async () => {
    const btn = $("#btn-save-ports");
    btn.disabled = true; btn.textContent = "保存中…";
    try {
      const res = await api("save_settings", Number($("#in-mixed-port").value), Number($("#in-ctl-port").value));
      if (res && res.ok === false) toast(res.error || "保存失敗", "error");
      else toast("已保存，核心已重啟", "ok");
      await refreshState();
    } catch (e) { toast(String(e), "error"); }
    btn.disabled = false; btn.textContent = "保存並重啟核心";
  });

  $("#btn-open-data").addEventListener("click", () => api("open_data_dir"));
  $("#btn-copy-logs").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#logbox").innerText);
      toast("已複製", "ok");
    } catch (e) { toast("複製失敗", "error"); }
  });
  $("#btn-check-update").addEventListener("click", () => checkForUpdates(true));
  $("#sw-auto-update").addEventListener("change", (ev) => {
    prefs.autoUpdateCheck = ev.target.checked;
    savePreferences();
  });
  $("#btn-open-update").addEventListener("click", () => {
    if (!latestUpdate || !latestUpdate.url) return;
    if (demo) window.open(latestUpdate.url, "_blank");
    else api("open_url", latestUpdate.url);
  });
  const closeDiagnostics = () => {
    $("#diagnostics-modal").classList.add("hidden");
    diagnosticsText = "";
  };
  $("#btn-export-diagnostics").addEventListener("click", async () => {
    if (demo) {
      toast("DEMO 模式不產生診斷資料", "error");
      return;
    }
    const btn = $("#btn-export-diagnostics");
    btn.disabled = true; btn.textContent = "產生預覽中…";
    try {
      const res = await api("diagnostics_preview");
      if (!res || !res.ok) {
        toast((res && res.error) || "無法產生診斷預覽", "error");
        return;
      }
      diagnosticsText = res.text || "";
      $("#diagnostics-preview").textContent = diagnosticsText;
      const summary = res.summary || {};
      $("#diagnostics-summary").textContent =
        `已去識別化：URL ${Number(summary.urls || 0)}、IP ${Number(summary.ips || 0)}、` +
        `端點 ${Number(summary.endpoints || 0)}、敏感欄位 ${Number(summary.secrets || 0)}。` +
        "請確認內容後再匯出。";
      $("#diagnostics-modal").classList.remove("hidden");
      $("#btn-confirm-export-diagnostics").focus();
    } catch (e) {
      toast(String(e), "error");
    } finally {
      btn.disabled = false; btn.textContent = "預覽／匯出診斷資料";
    }
  });
  $("#btn-confirm-export-diagnostics").addEventListener("click", async () => {
    const btn = $("#btn-confirm-export-diagnostics");
    btn.disabled = true; btn.textContent = "匯出中…";
    try {
      const res = await api("export_diagnostics");
      if (res && res.ok) {
        toast(`診斷資料已匯出：${res.path}`, "ok");
        closeDiagnostics();
      } else {
        toast((res && res.error) || "匯出失敗", "error");
      }
    } catch (e) {
      toast(String(e), "error");
    } finally {
      btn.disabled = false; btn.textContent = "確認匯出";
    }
  });
  $("#btn-copy-diagnostics").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(diagnosticsText);
      toast("已複製去識別化診斷內容", "ok");
    } catch (e) {
      toast("複製失敗", "error");
    }
  });
  $("#btn-close-diagnostics").addEventListener("click", closeDiagnostics);
  $("#btn-cancel-diagnostics").addEventListener("click", closeDiagnostics);
  $("#diagnostics-modal").addEventListener("click", (ev) => {
    if (ev.target === $("#diagnostics-modal")) closeDiagnostics();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("#diagnostics-modal").classList.contains("hidden")) closeDiagnostics();
  });

  $$("[data-open-url]").forEach((b) => b.addEventListener("click", () => {
    const url = b.dataset.openUrl;
    if (demo) window.open(url, "_blank");
    else api("open_url", url);
  }));
}

/* ---------- boot ---------- */

document.addEventListener("DOMContentLoaded", async () => {
  bindNav();
  bindActions();
  installUiCrashHandlers();
  await waitBridge();
  demo = !((window.pywebview && window.pywebview.api) || (window.__TAURI__ && window.__TAURI__.core));
  if (demo) {
    if (!new URLSearchParams(location.search).has("preview")) {
      $("#demo-banner").classList.remove("hidden");
    }
    sparkDown = Array.from({ length: 60 }, () => Math.random() * 320000);
    sparkUp = Array.from({ length: 60 }, () => Math.random() * 42000);
    if (!Object.keys(usageData.days).length) seedDemoStats();
  }

  await refreshState();
  drawSpark();
  renderStatsPage();
  initUpdateChecker();

  const wanted = new URLSearchParams(location.search).get("page");
  if (wanted && document.getElementById("page-" + wanted)) switchPage(wanted);

  setInterval(tickLive, 1000);
  setInterval(refreshState, 5000);
  setInterval(() => { if (page === "logs") refreshLogs(); }, 2000);
  setInterval(() => { if (page === "proxies" && state && state.running) refreshGroups(); }, 6000);

  window.addEventListener("resize", () => {
    drawSpark();
    if (page === "stats") drawStatsChart();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) saveUsageData(true);
  });
  window.addEventListener("pagehide", () => saveUsageData(true));
  window.addEventListener("beforeunload", () => saveUsageData(true));
});
