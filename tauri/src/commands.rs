use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::State;

use crate::core::{self, Core};
use crate::proxy;
use crate::state::{data_dir, Entry, Profiles, Store, APP_VERSION, TEST_URL};

pub struct AppState {
    pub store: Store,
    pub profiles: Profiles,
    pub core: Core,
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
    let s = state.lock().unwrap();
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
    if let Err(e) = s.profiles.update(&pid) {
        return err(e);
    }
    if s.store.data.active_profile == pid {
        if let Err(e) = do_reload(&mut *s) {
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
        Ok(d) => json!({
            "running": true,
            "up_total": d.get("uploadTotal").and_then(|v| v.as_u64()).unwrap_or(0),
            "down_total": d.get("downloadTotal").and_then(|v| v.as_u64()).unwrap_or(0),
            "count": d.get("connections").and_then(|v| v.as_array()).map(|a| a.len()).unwrap_or(0),
        }),
        Err(_) => json!({"running": false}),
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
    if url.starts_with("http://") || url.starts_with("https://") {
        let _ = open::that(url);
        ok()
    } else {
        err("無效的網址")
    }
}

#[tauri::command]
pub fn quit_app(app: tauri::AppHandle, state: State<'_, Shared>) -> Value {
    cleanup(&state);
    app.exit(0);
    ok()
}
