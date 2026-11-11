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

/* ---------- helpers ---------- */

function fmtBytes(n, perSec) {
  n = Number(n) || 0;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  const v = i === 0 ? Math.round(n) : n >= 100 ? n.toFixed(0) : n.toFixed(1);
  return v + " " + units[i] + (perSec ? "/s" : "");
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
  app_version: "0.2.0",
  data_dir: "C:\\Users\\…\\AppData\\Roaming\\KumoRoute",
  test_url: "https://cp.cloudflare.com/generate_204",
  profiles: [
    { id: "demo1", name: "範例機場", kind: "remote", updated_at: "2026-11-10 10:42:18" },
    { id: "direct", name: "內建直連（DIRECT）", kind: "builtin", updated_at: "2026-11-10 10:38:02" },
  ],
  active_profile: "demo1",
  totals: { down: 734003200, up: 28311552 },
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
  return {
    running: true,
    down_total: Math.round(demoCfg.totals.down),
    up_total: Math.round(demoCfg.totals.up),
    count: 24 + Math.round(Math.random() * 40),
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
    renderAll();
  } catch (e) {
    console.error(e);
  }
}

function renderAll() {
  if (!state) return;
  $("#foot-dot").className = "dot" + (state.running ? " on" : "");
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
  if (!state.running) { setSpeeds(0, 0, 0); return; }
  try {
    const live = demo ? demoLive() : await api("get_live");
    if (!live || !live.running) { setSpeeds(0, 0, 0); return; }
    const now = performance.now() / 1000;
    if (prevTotals && now - prevTotals.t > 0.2) {
      const dt = now - prevTotals.t;
      const down = Math.max(0, (live.down_total - prevTotals.down) / dt);
      const up = Math.max(0, (live.up_total - prevTotals.up) / dt);
      setSpeeds(down, up, live.count);
    }
    prevTotals = { t: now, down: live.down_total, up: live.up_total };
    $("#sp-down-total").textContent = fmtBytes(live.down_total);
    $("#sp-up-total").textContent = fmtBytes(live.up_total);
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

/* ---------- proxies ---------- */

async function refreshGroups() {
  try {
    if (!state || !state.running) { groups = []; renderGroups(); return; }
    const res = demo ? await demoApi("get_proxy_groups") : await api("get_proxy_groups");
    groups = (res && res.groups) || [];
    renderGroups();
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
      else toast("訂閱已更新", "ok");
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
          renderGroups();
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
      else toast("已切換配置", "ok");
      await refreshState();
      if (page === "proxies") await refreshGroups();
    } else if (act === "update") {
      btn.disabled = true; btn.textContent = "更新中…";
      const res = await api("update_profile", id);
      if (res && res.ok === false) toast(res.error || "更新失敗", "error");
      else toast("訂閱已更新", "ok");
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
      else toast("已刪除", "ok");
      await refreshState();
      if (page === "proxies") await refreshGroups();
    }
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
  await waitBridge();
  demo = !((window.pywebview && window.pywebview.api) || (window.__TAURI__ && window.__TAURI__.core));
  if (demo) {
    if (!new URLSearchParams(location.search).has("preview")) {
      $("#demo-banner").classList.remove("hidden");
    }
    sparkDown = Array.from({ length: 60 }, () => Math.random() * 320000);
    sparkUp = Array.from({ length: 60 }, () => Math.random() * 42000);
  }

  await refreshState();
  drawSpark();

  const wanted = new URLSearchParams(location.search).get("page");
  if (wanted && document.getElementById("page-" + wanted)) switchPage(wanted);

  setInterval(() => { if (page === "overview") tickLive(); }, 1000);
  setInterval(refreshState, 5000);
  setInterval(() => { if (page === "logs") refreshLogs(); }, 2000);
  setInterval(() => { if (page === "proxies" && state && state.running) refreshGroups(); }, 6000);
});
