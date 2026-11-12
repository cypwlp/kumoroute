use std::fs;
use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::State;

use crate::core::{self, Core};
use crate::proxy::{self, ProxyRecovery};
use crate::state::{data_dir, Entry, Profiles, Store, APP_VERSION, SUB_UA, TEST_URL};

pub struct AppState {
    pub store: Store,
    pub profiles: Profiles,
    pub core: Core,
    pub proxy_recovery: Option<ProxyRecovery>,
}

pub type Shared = Mutex<AppState>;

fn ok() -> Value {
    json!({"ok": true})
}
fn err(msg: impl Into<String>) -> Value {
    json!({"ok": false, "error": msg.into()})
}

fn public_entry(e: &Entry) -> Value {
    json!({"id": e.id, "name": e.name, "kind": e.kind, "updated_at": e.updated_at})
}

fn do_start(s: &mut AppState) -> Result<(), String> {
    let port = s.store.data.controller_port;
    let rt = s.profiles.build_runtime(&s.store)?;
    s.core.start(port, rt)
}

fn do_reload(s: &mut AppState) -> Result<(), String> {
    let port = s.store.data.controller_port;
    let rt = s.profiles.build_runtime(&s.store)?;
    s.core.reload(port, rt)
}

pub fn cleanup(state: &Shared) {
    let mut s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    if proxy::is_on(&s.store) || s.store.data.original_proxy.is_some() {
        let _ = proxy::set_system_proxy(&mut s.store, false, core::is_up(port));
    }
    s.core.stop();
}

#[tauri::command]
pub fn get_state(state: State<'_, Shared>) -> Value {
    let mut s = state.lock().unwrap();
    let proxy_recovery = s.proxy_recovery.take();
    let port = s.store.data.controller_port;
    let running = core::is_up(port);
    let mut mode = s.store.data.mode.clone();
    if running {
        if let Ok(cfg) = core::api("GET", port, "/configs", None, 4) {
            if let Some(m) = cfg.get("mode").and_then(|v| v.as_str()) {
                mode = m.to_string();
            }
        }
    }
    let active = s.profiles.active_entry(&s.store);
    json!({
        "app_version": APP_VERSION,
        "core_version": if running { core::version(port) } else { None },
        "running": running,
        "sys_proxy": proxy::is_on(&s.store),
        "mode": mode,
        "mixed_port": s.store.data.mixed_port,
        "controller_port": port,
        "active_profile": public_entry(&active),
        "profiles": s.profiles.entries.iter().map(public_entry).collect::<Vec<_>>(),
        "data_dir": data_dir().to_string_lossy(),
        "core_found": crate::state::core_binary().is_some(),
        "test_url": TEST_URL,
        "proxy_recovery": proxy_recovery,
    })
}

#[tauri::command]
pub fn start_core(state: State<'_, Shared>) -> Value {
    let mut s = state.lock().unwrap();
    match do_start(&mut *s) {
        Ok(_) => ok(),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn stop_core(state: State<'_, Shared>) -> Value {
    let mut s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    if proxy::is_on(&s.store) {
        let _ = proxy::set_system_proxy(&mut s.store, false, core::is_up(port));
    }
    s.core.stop();
    ok()
}

#[tauri::command]
pub fn set_mode(state: State<'_, Shared>, mode: String) -> Value {
    if !["rule", "global", "direct"].contains(&mode.as_str()) {
        return err("無效的模式");
    }
    let mut s = state.lock().unwrap();
    s.store.data.mode = mode.clone();
    let _ = s.store.save();
    let port = s.store.data.controller_port;
    if core::is_up(port) {
        if let Err(e) = core::api("PATCH", port, "/configs", Some(json!({"mode": mode})), 6) {
            return err(e);
        }
    }
    ok()
}

#[tauri::command]
pub fn set_system_proxy(state: State<'_, Shared>, enabled: bool) -> Value {
    let mut s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    let mut up = core::is_up(port);
    if enabled && !up {
        if let Err(e) = do_start(&mut *s) {
            return err(format!("核心啟動失敗：{e}"));
        }
        up = true;
    }
    match proxy::set_system_proxy(&mut s.store, enabled, up) {
        Ok(on) => json!({"ok": true, "sys_proxy": on}),
        Err(e) => json!({"ok": false, "error": e, "sys_proxy": false}),
    }
}

#[tauri::command]
pub fn get_proxy_groups(state: State<'_, Shared>) -> Value {
    let s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    if !core::is_up(port) {
        return json!({"ok": true, "groups": []});
    }
    let data = match core::api("GET", port, "/proxies", None, 8) {
        Ok(d) => d,
        Err(e) => return json!({"ok": false, "error": e, "groups": []}),
    };
    let proxies = data.get("proxies").and_then(|v| v.as_object()).cloned().unwrap_or_default();
    let mut groups: Vec<Value> = Vec::new();
    for (name, p) in &proxies {
        let t = p.get("type").and_then(|v| v.as_str()).unwrap_or("");
        if !["Selector", "URLTest", "Fallback", "LoadBalance", "Relay"].contains(&t) {
            continue;
        }
        let nodes: Vec<Value> = p
            .get("all")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|n| n.as_str())
                    .map(|n| {
                        let nt = proxies.get(n).and_then(|x| x.get("type")).and_then(|v| v.as_str()).unwrap_or("");
                        json!({"name": n, "type": nt})
                    })
                    .collect()
            })
            .unwrap_or_default();
        groups.push(json!({
            "name": name,
            "type": t,
            "now": p.get("now").and_then(|v| v.as_str()).unwrap_or(""),
            "nodes": nodes,
        }));
    }
    groups.sort_by(|a, b| {
        let an = a["name"].as_str().unwrap_or("");
        let bn = b["name"].as_str().unwrap_or("");
        (an == "GLOBAL", an.to_lowercase()).cmp(&(bn == "GLOBAL", bn.to_lowercase()))
    });
    json!({"ok": true, "groups": groups})
}

#[tauri::command]
pub fn select_proxy(state: State<'_, Shared>, group: String, name: String) -> Value {
    let s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    let path = format!("/proxies/{}", urlencoding::encode(&group));
    match core::api("PUT", port, &path, Some(json!({"name": name})), 6) {
        Ok(_) => ok(),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn test_group_delay(state: State<'_, Shared>, group: String) -> Value {
    let s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    let path = format!(
        "/group/{}/delay?timeout=5000&url={}",
        urlencoding::encode(&group),
        urlencoding::encode(TEST_URL)
    );
    match core::api("GET", port, &path, None, 14) {
        Ok(d) => json!({"ok": true, "delays": d}),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn add_subscription(state: State<'_, Shared>, url: String, name: String) -> Value {
    let mut s = state.lock().unwrap();
    match s.profiles.add_remote(&url, &name) {
        Ok(entry) => {
            s.store.data.active_profile = entry.id.clone();
            let _ = s.store.save();
            if let Err(e) = do_reload(&mut *s) {
                return err(e);
            }
            json!({"ok": true, "entry": public_entry(&entry)})
        }
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn import_profile(state: State<'_, Shared>) -> Value {
    let picked = rfd::FileDialog::new()
        .add_filter("Clash 配置", &["yaml", "yml"])
        .add_filter("所有檔案", &["*"])
        .pick_file();
    let Some(path) = picked else {
        return json!({"ok": false, "cancelled": true});
    };
    let mut s = state.lock().unwrap();
    match s.profiles.add_local(&path.to_string_lossy()) {
        Ok(entry) => {
            s.store.data.active_profile = entry.id.clone();
            let _ = s.store.save();
            if let Err(e) = do_reload(&mut *s) {
                return err(e);
            }
            json!({"ok": true, "entry": public_entry(&entry)})
        }
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn update_profile(state: State<'_, Shared>, pid: String) -> Value {
    let mut s = state.lock().unwrap();
    let previous = s.profiles.get(&pid).cloned();
    if let Err(e) = s.profiles.update(&pid) {
        return err(e);
    }
    if s.store.data.active_profile == pid {
        if let Err(e) = do_reload(&mut *s) {
            if let Some(previous) = previous {
                return match s.profiles.rollback_to(&pid, &previous) {
                    Ok(()) => {
                        let _ = do_reload(&mut *s);
                        err(format!("更新失敗，已自動回滾：{e}"))
                    }
                    Err(rollback_error) => err(format!(
                        "更新失敗：{e}；自動回滾也失敗：{rollback_error}"
                    )),
                };
            }
            return err(e);
        }
    }
    ok()
}

#[tauri::command]
pub fn delete_profile(state: State<'_, Shared>, pid: String) -> Value {
    let mut s = state.lock().unwrap();
    let was_active = s.store.data.active_profile == pid;
    {
        let a = &mut *s;
        if let Err(e) = a.profiles.delete(&pid, &mut a.store) {
            return err(e);
        }
    }
    if was_active {
        if let Err(e) = do_reload(&mut *s) {
            return err(e);
        }
    }
    ok()
}

#[tauri::command]
pub fn set_active_profile(state: State<'_, Shared>, pid: String) -> Value {
    let mut s = state.lock().unwrap();
    if s.profiles.get(&pid).is_none() {
        return err("找不到該配置");
    }
    s.store.data.active_profile = pid;
    let _ = s.store.save();
    match do_reload(&mut *s) {
        Ok(_) => ok(),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn get_live(state: State<'_, Shared>) -> Value {
    let s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    if !core::is_up(port) {
        return json!({"running": false});
    }
    match core::api("GET", port, "/connections", None, 5) {
        Ok(d) => {
            let raw = d.get("connections").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            let connections: Vec<Value> = raw
                .iter()
                .map(|c| {
                    let meta = c.get("metadata").cloned().unwrap_or_else(|| json!({}));
                    json!({
                        "id": c.get("id").and_then(|v| v.as_str()).unwrap_or(""),
                        "upload": c.get("upload").and_then(|v| v.as_u64()).unwrap_or(0),
                        "download": c.get("download").and_then(|v| v.as_u64()).unwrap_or(0),
                        "host": meta
                            .get("host")
                            .and_then(|v| v.as_str())
                            .or_else(|| meta.get("destinationIP").and_then(|v| v.as_str()))
                            .unwrap_or(""),
                        "rule": c.get("rule").and_then(|v| v.as_str()).unwrap_or(""),
                        "rulePayload": c.get("rulePayload").and_then(|v| v.as_str()).unwrap_or(""),
                        "chains": c.get("chains").cloned().unwrap_or_else(|| json!([])),
                    })
                })
                .collect();
            json!({
                "running": true,
                "up_total": d.get("uploadTotal").and_then(|v| v.as_u64()).unwrap_or(0),
                "down_total": d.get("downloadTotal").and_then(|v| v.as_u64()).unwrap_or(0),
                "count": raw.len(),
                "connections": connections,
            })
        }
        Err(_) => json!({"running": false}),
    }
}

#[tauri::command]
pub fn save_stats_export(format: String, content: String) -> Value {
    let ext = if format.eq_ignore_ascii_case("csv") { "csv" } else { "json" };
    let folder = dirs::download_dir()
        .or_else(|| dirs::home_dir().map(|p| p.join("Downloads")))
        .unwrap_or_else(data_dir);
    if let Err(e) = fs::create_dir_all(&folder) {
        return err(format!("無法建立下載資料夾：{e}"));
    }
    let name = format!(
        "KumoRoute-stats-{}.{}",
        chrono::Local::now().format("%Y%m%d-%H%M%S"),
        ext
    );
    let path = folder.join(name);
    let bytes = if ext == "csv" {
        format!("\u{feff}{content}").into_bytes()
    } else {
        content.into_bytes()
    };
    match fs::write(&path, bytes) {
        Ok(_) => json!({"ok": true, "path": path.to_string_lossy()}),
        Err(e) => err(format!("匯出失敗：{e}")),
    }
}

#[tauri::command]
pub fn check_update() -> Value {
    let response = ureq::get("https://api.github.com/repos/cypwlp/kumoroute/releases/latest")
        .set("User-Agent", SUB_UA)
        .set("Accept", "application/vnd.github+json")
        .timeout(std::time::Duration::from_secs(12))
        .call();
    let release: Value = match response {
        Ok(r) => match r.into_json::<Value>() {
            Ok(v) => v,
            Err(e) => return err(format!("解析更新資訊失敗：{e}")),
        },
        Err(e) => return err(format!("檢查更新失敗：{e}")),
    };
    let latest = release
        .get("tag_name")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim_start_matches('v');
    let current = APP_VERSION.trim_start_matches('v');
    let number_key = |value: &str| -> Vec<u64> {
        regex::Regex::new(r"\d+")
            .unwrap()
            .find_iter(value)
            .map(|m| m.as_str().parse::<u64>().unwrap_or(0))
            .collect()
    };
    let mut latest_key = number_key(latest);
    let mut current_key = number_key(current);
    latest_key.resize(4, 0);
    current_key.resize(4, 0);
    json!({
        "ok": true,
        "current": current,
        "latest": latest,
        "update_available": latest_key > current_key,
        "url": release.get("html_url").and_then(|v| v.as_str()).unwrap_or("https://github.com/cypwlp/kumoroute/releases/latest"),
        "published_at": release.get("published_at").and_then(|v| v.as_str()).unwrap_or(""),
        "notes": release.get("body").and_then(|v| v.as_str()).unwrap_or("").chars().take(4000).collect::<String>(),
    })
}

#[tauri::command]
pub fn record_ui_error(message: String, stack: String) -> Value {
    crate::state::write_crash("ui", &format!("{message}\n{stack}"));
    ok()
}

fn read_tail(path: &std::path::Path, limit: usize) -> String {
    let data = fs::read(path).unwrap_or_default();
    let start = data.len().saturating_sub(limit);
    String::from_utf8_lossy(&data[start..]).to_string()
}

fn diagnostics_text(s: &AppState) -> Result<(String, crate::state::RedactionSummary), String> {
    let port = s.store.data.controller_port;
    let running = core::is_up(port);
    let logs_dir = data_dir().join("logs");
    let mut text = format!(
        "KumoRoute Diagnostics\ngenerated_at: {}\napp_version: {}\nplatform: {} {}\ncore_running: {}\ncore_version: {}\nsystem_proxy: {}\nmode: {}\nmixed_port: {}\ncontroller_port: {}\nprofiles: {}\nactive_profile_kind: {}\n",
        crate::state::now(),
        APP_VERSION,
        std::env::consts::OS,
        std::env::consts::ARCH,
        running,
        if running { core::version(port).unwrap_or_default() } else { "-".into() },
        proxy::is_on(&s.store),
        s.store.data.mode,
        s.store.data.mixed_port,
        port,
        s.profiles.entries.len(),
        s.profiles.active_entry(&s.store).kind,
    );
    for (label, file) in [
        ("APP LOG", logs_dir.join("app.log")),
        ("CORE LOG", logs_dir.join("core.log")),
        ("CRASH LOG", logs_dir.join("crash.log")),
    ] {
        let body = read_tail(&file, 131072);
        text.push_str(&format!("\n===== {label} =====\n{body}\n"));
    }
    let report = crate::state::sanitize_diagnostics_report(&text);
    Ok((report.text, report.summary))
}

#[tauri::command]
pub fn diagnostics_preview(state: State<'_, Shared>) -> Value {
    let s = state.lock().unwrap_or_else(|e| e.into_inner());
    match diagnostics_text(&s) {
        Ok((text, summary)) => json!({
            "ok": true,
            "text": text,
            "summary": summary,
        }),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn export_diagnostics(state: State<'_, Shared>) -> Value {
    let s = state.lock().unwrap_or_else(|e| e.into_inner());
    let (text, _) = match diagnostics_text(&s) {
        Ok(value) => value,
        Err(e) => return err(e),
    };
    let folder = dirs::download_dir()
        .or_else(|| dirs::home_dir().map(|p| p.join("Downloads")))
        .unwrap_or_else(data_dir);
    if let Err(e) = fs::create_dir_all(&folder) {
        return err(format!("無法建立下載資料夾：{e}"));
    }
    let path = folder.join(format!(
        "KumoRoute-diagnostics-{}.txt",
        chrono::Local::now().format("%Y%m%d-%H%M%S")
    ));
    match fs::write(&path, text) {
        Ok(_) => json!({"ok": true, "path": path.to_string_lossy()}),
        Err(e) => err(format!("匯出診斷資料失敗：{e}")),
    }
}

#[tauri::command]
pub fn get_logs() -> Value {
    json!({"ok": true, "lines": core::log_lines(300)})
}

#[tauri::command]
pub fn save_settings(state: State<'_, Shared>, mixed_port: u16, controller_port: u16) -> Value {
    let mut s = state.lock().unwrap();
    if !(1024..=65535).contains(&mixed_port) || !(1024..=65535).contains(&controller_port) {
        return err("連接埠必須在 1024–65535 之間");
    }
    if mixed_port == controller_port {
        return err("兩個連接埠不能相同");
    }
    let changed_mixed = mixed_port != s.store.data.mixed_port;
    let changed_ctl = controller_port != s.store.data.controller_port;
    s.store.data.mixed_port = mixed_port;
    s.store.data.controller_port = controller_port;
    let _ = s.store.save();
    let was_running = core::is_up(s.store.data.controller_port);
    if was_running && (changed_mixed || changed_ctl) {
        s.core.stop();
        if let Err(e) = do_start(&mut *s) {
            return err(e);
        }
    }
    if changed_mixed && proxy::is_on(&s.store) {
        let _ = proxy::apply(1, &format!("127.0.0.1:{mixed_port}"), proxy::PROXY_OVERRIDE);
    }
    ok()
}

#[tauri::command]
pub fn open_data_dir() -> Value {
    match open::that(data_dir()) {
        Ok(_) => ok(),
        Err(e) => err(e.to_string()),
    }
}

#[tauri::command]
pub fn open_url(url: String) -> Value {
    let Ok(parsed) = url::Url::parse(url.trim()) else {
        return err("無效的網址");
    };
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.host_str().is_none()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return err("只允許不含帳密的 HTTP(S) 網址");
    }
    match open::that(parsed.as_str()) {
        Ok(()) => ok(),
        Err(e) => err(e.to_string()),
    }
}

#[tauri::command]
pub fn quit_app(app: tauri::AppHandle, state: State<'_, Shared>) -> Value {
    cleanup(&state);
    app.exit(0);
    ok()
}
