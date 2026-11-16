use std::fs::{self, File};
use std::io::{Read, Write};
use std::net::{Ipv6Addr, SocketAddr, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tauri::State;

use crate::core::{self, Core};
use crate::proxy::{self, ProxyRecovery};
use crate::state::{data_dir, Entry, Profiles, Store, APP_VERSION, SUB_UA, TEST_URL};

#[cfg(windows)]
use windows::core::{PCWSTR, PWSTR};
#[cfg(windows)]
use windows::Win32::Foundation::FILETIME;
#[cfg(windows)]
use windows::Win32::NetworkManagement::Rras::{
    RasDialW, RasHangUpW, HRASCONN, RASDIALPARAMSW,
};
#[cfg(windows)]
use windows::Win32::Security::Credentials::{
    CredDeleteW, CredFree, CredReadW, CredWriteW, CREDENTIALW, CRED_FLAGS,
    CRED_PERSIST_LOCAL_MACHINE, CRED_TYPE_GENERIC,
};

#[derive(Clone)]
pub struct UpdateDownloadState {
    cancel: Arc<AtomicBool>,
    status: Arc<Mutex<Value>>,
}

impl Default for UpdateDownloadState {
    fn default() -> Self {
        Self {
            cancel: Arc::new(AtomicBool::new(false)),
            status: Arc::new(Mutex::new(json!({
                "active": false,
                "phase": "idle",
                "received": 0,
                "total": 0,
                "percent": 0,
                "path": null,
                "error": null
            }))),
        }
    }
}

impl UpdateDownloadState {
    fn snapshot(&self) -> Value {
        self.status.lock().map(|v| v.clone()).unwrap_or_else(|_| json!({
            "active": false,
            "phase": "error",
            "received": 0,
            "total": 0,
            "percent": 0,
            "path": null,
            "error": "更新狀態鎖定失敗"
        }))
    }

    fn update(&self, value: Value) {
        if let Ok(mut status) = self.status.lock() {
            *status = value;
        }
    }
}

pub struct AppState {
    pub store: Store,
    pub profiles: Profiles,
    pub core: Core,
    pub proxy_recovery: Option<ProxyRecovery>,
    pub update_download: UpdateDownloadState,
}

pub type Shared = Mutex<AppState>;

fn ok() -> Value {
    json!({"ok": true})
}
fn err(msg: impl Into<String>) -> Value {
    json!({"ok": false, "error": msg.into()})
}

fn safe_update_url(value: &str) -> bool {
    let Ok(parsed) = url::Url::parse(value.trim()) else {
        return false;
    };
    matches!(parsed.scheme(), "https")
        && matches!(parsed.host_str(), Some("github.com" | "objects.githubusercontent.com" | "release-assets.githubusercontent.com"))
        && parsed.username().is_empty()
        && parsed.password().is_none()
}

fn install_mode() -> &'static str {
    if std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.join("KumoRoute.portable")))
        .map(|marker| marker.is_file())
        .unwrap_or(false)
    {
        "portable"
    } else {
        "installed"
    }
}

fn update_asset_score(filename: &str, os: &str, prefer_zip: bool) -> Option<u8> {
    let name = filename.to_ascii_lowercase();
    if !name.starts_with("kumoroute-") {
        return None;
    }
    match os {
        "windows" if name.ends_with("-setup.exe") => Some(if prefer_zip { 1 } else { 0 }),
        "windows" if name.ends_with(".zip") => Some(if prefer_zip { 0 } else { 1 }),
        "macos" if name.ends_with(".dmg") => Some(0),
        "linux" if name.ends_with(".appimage") => Some(0),
        "linux" if name.ends_with(".deb") => Some(1),
        _ => None,
    }
}

fn update_asset(release: &Value, prefer_zip: bool) -> Option<Value> {
    let assets = release.get("assets")?.as_array()?;
    let os = std::env::consts::OS;
    let mut checksum_url: Option<String> = None;
    let mut selected: Option<(u8, String, String, u64)> = None;
    for item in assets {
        let name = item.get("name").and_then(Value::as_str).unwrap_or("").to_string();
        let url = item.get("browser_download_url").and_then(Value::as_str).unwrap_or("");
        if name == "SHA256SUMS.txt" && safe_update_url(url) {
            checksum_url = Some(url.to_string());
        }
        let Some(score) = update_asset_score(&name, os, prefer_zip) else {
            continue;
        };
        if !safe_update_url(url) {
            continue;
        }
        let size = item.get("size").and_then(Value::as_u64).unwrap_or(0);
        if selected.as_ref().map(|v| score < v.0).unwrap_or(true) {
            selected = Some((score, name, url.to_string(), size));
        }
    }
    let (_, filename, download_url, size) = selected?;
    Some(json!({
        "filename": filename,
        "download_url": download_url,
        "size": size,
        "size_mb": (size as f64 / 1048576.0 * 10.0).round() / 10.0,
        "sha256_url": checksum_url.unwrap_or_default(),
    }))
}

fn parse_sha256sums(text: &str, filename: &str) -> Option<String> {
    for line in text.lines() {
        let mut parts = line.split_whitespace();
        let digest = parts.next()?.trim_start_matches('*');
        let name = parts.next()?.trim_start_matches('*');
        if name == filename && digest.len() == 64 && digest.chars().all(|c| c.is_ascii_hexdigit()) {
            return Some(digest.to_ascii_lowercase());
        }
    }
    None
}

fn hidden_command(program: &str) -> Command {
    #[allow(unused_mut)]
    let mut command = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    command
}

const VPN_REGISTRY_KEY: &str =
    r"SYSTEM\CurrentControlSet\Services\RasMan\Parameters\Config\VpnCostedNetworkSettings";

const VPN_POWERSHELL_SCRIPT: &str = r#"
$ErrorActionPreference = 'SilentlyContinue'
$items = @()
$items += Get-VpnConnection
$items += Get-VpnConnection -AllUserConnection
$advanced = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\RasMan\Parameters\Config\VpnCostedNetworkSettings'
[pscustomobject]@{
  Connections = @($items | Sort-Object Name -Unique | Select-Object Name,ServerAddress,TunnelType,ConnectionStatus,RememberCredential,AllUserConnection)
  AllowMetered = -not [bool]$advanced.NoCostedNetwork
  AllowRoaming = -not [bool]$advanced.NoRoamingNetwork
} | ConvertTo-Json -Depth 5 -Compress
"#;

const VPN_CREDENTIAL_PREFIX: &str = "KumoRoute/VPN/";

#[derive(Clone)]
struct VpnCredential {
    username: String,
    password: String,
}

fn vpn_credential_target(name: &str) -> String {
    format!("{VPN_CREDENTIAL_PREFIX}{}", name.trim())
}

fn ps_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn vpn_tunnel(value: &str) -> Option<&'static str> {
    match value.trim().to_ascii_lowercase().as_str() {
        "pptp" => Some("Pptp"),
        "l2tp" => Some("L2tp"),
        "ikev2" => Some("Ikev2"),
        "sstp" => Some("Sstp"),
        "automatic" => Some("Automatic"),
        _ => None,
    }
}

fn vpn_profile_command(script: &str) -> Result<(), String> {
    let output = hidden_command("powershell.exe")
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", &format!("$ErrorActionPreference='Stop'; {script}")])
        .output()
        .map_err(|e| e.to_string())?;
    if output.status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
    Err(if detail.is_empty() {
        format!("PowerShell 結束代碼 {}", output.status.code().unwrap_or(-1))
    } else {
        detail
    })
}

fn vpn_ras_error(code: u32) -> String {
    match code {
        645 => "Windows VPN 驗證失敗".into(),
        691 => "使用者名稱或密碼錯誤".into(),
        720 => "PPP 連線協商失敗".into(),
        809 => "VPN 連線逾時或伺服器無回應".into(),
        868 => "找不到 VPN 伺服器".into(),
        _ => format!("VPN 連線失敗（錯誤 {code}）"),
    }
}

#[cfg(windows)]
fn wide_string(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
fn copy_wide(dst: &mut [u16], value: &str) {
    let limit = dst.len().saturating_sub(1);
    for (slot, ch) in dst.iter_mut().zip(value.encode_utf16().take(limit)) {
        *slot = ch;
    }
    if let Some(last) = dst.last_mut() {
        *last = 0;
    }
}

#[cfg(windows)]
unsafe fn pwstr_string(value: PWSTR) -> String {
    if value.0.is_null() {
        return String::new();
    }
    let mut len = 0usize;
    while *value.0.add(len) != 0 {
        len += 1;
    }
    String::from_utf16_lossy(std::slice::from_raw_parts(value.0, len))
}

#[cfg(windows)]
fn vpn_credential_read(name: &str) -> Result<Option<VpnCredential>, String> {
    let target = wide_string(&vpn_credential_target(name));
    let mut raw: *mut CREDENTIALW = std::ptr::null_mut();
    if unsafe { CredReadW(PCWSTR(target.as_ptr()), CRED_TYPE_GENERIC, 0, &mut raw) }.is_err()
        || raw.is_null()
    {
        return Ok(None);
    }
    let item = unsafe { &*raw };
    let username = unsafe { pwstr_string(item.UserName) };
    let password = if item.CredentialBlob.is_null() || item.CredentialBlobSize == 0 {
        String::new()
    } else {
        let bytes = unsafe {
            std::slice::from_raw_parts(item.CredentialBlob, item.CredentialBlobSize as usize)
        };
        let words: Vec<u16> = bytes
            .chunks_exact(2)
            .map(|chunk| u16::from_le_bytes([chunk[0], chunk[1]]))
            .collect();
        String::from_utf16_lossy(&words)
    };
    unsafe { CredFree(raw.cast()) };
    Ok(Some(VpnCredential { username, password }))
}

#[cfg(not(windows))]
fn vpn_credential_read(_name: &str) -> Result<Option<VpnCredential>, String> {
    Ok(None)
}

#[cfg(windows)]
fn vpn_credential_write(name: &str, username: &str, password: &str) -> Result<(), String> {
    let mut target = wide_string(&vpn_credential_target(name));
    let mut user = wide_string(username);
    let mut blob: Vec<u8> = password
        .encode_utf16()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    let item = CREDENTIALW {
        Flags: CRED_FLAGS(0),
        Type: CRED_TYPE_GENERIC,
        TargetName: PWSTR(target.as_mut_ptr()),
        Comment: PWSTR::null(),
        LastWritten: FILETIME::default(),
        CredentialBlobSize: blob.len() as u32,
        CredentialBlob: blob.as_mut_ptr(),
        Persist: CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount: 0,
        Attributes: std::ptr::null_mut(),
        TargetAlias: PWSTR::null(),
        UserName: PWSTR(user.as_mut_ptr()),
    };
    unsafe { CredWriteW(&item, 0) }.map_err(|e| format!("保存 Windows VPN 憑證失敗：{e}"))
}

#[cfg(not(windows))]
fn vpn_credential_write(_name: &str, _username: &str, _password: &str) -> Result<(), String> {
    Err("Windows VPN 僅支援 Windows".into())
}

#[cfg(windows)]
fn vpn_credential_delete(name: &str) {
    let target = wide_string(&vpn_credential_target(name));
    let _ = unsafe { CredDeleteW(PCWSTR(target.as_ptr()), CRED_TYPE_GENERIC, 0) };
}

#[cfg(not(windows))]
fn vpn_credential_delete(_name: &str) {}

fn prepare_vpn_proxy(s: &mut AppState) -> Result<bool, String> {
    if !s.store.data.vpn_disable_system_proxy || !proxy::is_on(&s.store) {
        return Ok(false);
    }
    let port = s.store.data.controller_port;
    proxy::set_system_proxy(&mut s.store, false, core::is_up(port))?;
    s.store.data.vpn_proxy_pending = true;
    let _ = s.store.save();
    Ok(true)
}

fn restore_vpn_proxy(s: &mut AppState) -> bool {
    if !s.store.data.vpn_proxy_pending {
        return false;
    }
    if !s.store.data.vpn_restore_system_proxy {
        s.store.data.vpn_proxy_pending = false;
        let _ = s.store.save();
        return false;
    }
    let port = s.store.data.controller_port;
    if !proxy::set_system_proxy(&mut s.store, true, core::is_up(port)).unwrap_or(false) {
        return false;
    }
    s.store.data.vpn_proxy_pending = false;
    let _ = s.store.save();
    true
}

fn test_ipv6_connectivity() -> bool {
    let addr = SocketAddr::new(Ipv6Addr::new(0x2606, 0x4700, 0x4700, 0, 0, 0, 0, 0x1111).into(), 443);
    TcpStream::connect_timeout(&addr, Duration::from_secs(2)).is_ok()
}

fn system_dns_servers() -> Vec<String> {
    let output = hidden_command("powershell.exe")
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
            "Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ServerAddresses -Unique"])
        .output();
    let mut values: Vec<String> = output
        .ok()
        .map(|out| String::from_utf8_lossy(&out.stdout).lines().map(|v| v.trim().to_string()).filter(|v| !v.is_empty()).collect())
        .unwrap_or_default();
    values.sort();
    values.dedup();
    values
}

fn doh_template_count() -> u64 {
    hidden_command("powershell.exe")
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue | Measure-Object).Count"])
        .output()
        .ok()
        .and_then(|out| String::from_utf8_lossy(&out.stdout).trim().parse().ok())
        .unwrap_or(0)
}

fn collect_dns_protocols(value: &serde_yaml::Value, doh: &mut u64, dot: &mut u64) {
    match value {
        serde_yaml::Value::String(text) => {
            let text = text.trim().to_ascii_lowercase();
            if text.starts_with("https://") || text.starts_with("quic://") {
                *doh += 1;
            } else if text.starts_with("tls://") {
                *dot += 1;
            }
        }
        serde_yaml::Value::Sequence(items) => {
            for item in items {
                collect_dns_protocols(item, doh, dot);
            }
        }
        serde_yaml::Value::Mapping(map) => {
            for item in map.values() {
                collect_dns_protocols(item, doh, dot);
            }
        }
        _ => {}
    }
}

fn configured_dns_protocols() -> (u64, u64) {
    let Ok(text) = fs::read_to_string(data_dir().join("runtime.yaml")) else {
        return (0, 0);
    };
    let Ok(cfg) = serde_yaml::from_str::<serde_yaml::Value>(&text) else {
        return (0, 0);
    };
    let Some(dns) = cfg
        .as_mapping()
        .and_then(|map| map.get(serde_yaml::Value::String("dns".into())))
    else {
        return (0, 0);
    };
    let mut doh = 0;
    let mut dot = 0;
    collect_dns_protocols(dns, &mut doh, &mut dot);
    (doh, dot)
}

fn merge_network_issue(issues: &mut Vec<Value>, kind: &str, count: u64, message: &str) {
    if let Some(existing) = issues.iter_mut().find(|item| item.get("type").and_then(Value::as_str) == Some(kind)) {
        let previous = existing.get("count").and_then(Value::as_u64).unwrap_or(0);
        existing["count"] = json!(previous.saturating_add(count.max(1)));
        existing["message"] = json!(message);
    } else {
        issues.push(json!({"type": kind, "count": count.max(1), "message": message}));
    }
}

fn grouped_network_issues(lines: &[String]) -> Vec<Value> {
    let mut ipv6 = 0u64;
    let mut dns = 0u64;
    let mut timeout = 0u64;
    for line in lines {
        let low = line.to_lowercase();
        let ipv6_text = low.contains("ipv6") || low.contains("unreachable network");
        let network_error = ["error", "fail", "unreachable", "timeout", "deadline exceeded", "refused"]
            .iter()
            .any(|word| low.contains(word));
        if ipv6_text && network_error { ipv6 += 1; }
        if low.contains("dns") && network_error { dns += 1; }
        if low.contains("timeout") || low.contains("deadline exceeded") { timeout += 1; }
    }
    let mut out = Vec::new();
    if ipv6 > 0 { out.push(json!({"type": "ipv6", "count": ipv6, "message": "IPv6 連線不可達"})); }
    if dns > 0 { out.push(json!({"type": "dns", "count": dns, "message": "DNS 解析失敗"})); }
    if timeout > 0 { out.push(json!({"type": "timeout", "count": timeout, "message": "連線逾時"})); }
    out
}

#[cfg(windows)]
fn vpn_ras_dial(name: &str, username: &str, password: &str) -> Result<(), (u32, String)> {
    let mut params = RASDIALPARAMSW::default();
    params.dwSize = std::mem::size_of::<RASDIALPARAMSW>() as u32;
    copy_wide(&mut params.szEntryName, name);
    copy_wide(&mut params.szUserName, username);
    copy_wide(&mut params.szPassword, password);
    let mut connection = HRASCONN::default();
    let code = unsafe { RasDialW(None, PCWSTR::null(), &params, 0, None, &mut connection) };
    if code == 0 {
        return Ok(());
    }
    if !connection.is_invalid() {
        let _ = unsafe { RasHangUpW(connection) };
    }
    Err((code, vpn_ras_error(code)))
}

#[cfg(not(windows))]
fn vpn_ras_dial(_name: &str, _username: &str, _password: &str) -> Result<(), (u32, String)> {
    Err((0, "Windows VPN 僅支援 Windows".into()))
}

fn vpn_snapshot() -> Result<(Vec<Value>, Value), String> {
    if std::env::consts::OS != "windows" {
        return Ok((Vec::new(), json!({"allow_metered": true, "allow_roaming": true})));
    }
    let output = hidden_command("powershell.exe")
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", VPN_POWERSHELL_SCRIPT])
        .output()
        .map_err(|e| format!("讀取 Windows VPN 失敗：{e}"))?;
    let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if raw.is_empty() {
        if !output.status.success() {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
            return Err(if detail.is_empty() {
                format!("讀取 Windows VPN 失敗（代碼 {}）", output.status.code().unwrap_or(-1))
            } else {
                format!("讀取 Windows VPN 失敗：{detail}")
            });
        }
        return Ok((Vec::new(), json!({"allow_metered": true, "allow_roaming": true})));
    }
    let parsed: Value = serde_json::from_str(&raw).map_err(|e| format!("解析 Windows VPN 失敗：{e}"))?;
    let allow_metered = parsed.get("AllowMetered").and_then(Value::as_bool).unwrap_or(true);
    let allow_roaming = parsed.get("AllowRoaming").and_then(Value::as_bool).unwrap_or(true);
    let raw_connections = parsed
        .get("Connections")
        .cloned()
        .or_else(|| if parsed.is_array() { Some(parsed.clone()) } else { None })
        .unwrap_or_else(|| Value::Array(Vec::new()));
    let items = raw_connections.as_array().cloned().unwrap_or_else(|| {
        if raw_connections.is_object() { vec![raw_connections] } else { Vec::new() }
    });

    let mut connections = Vec::new();
    for item in items {
        let name = item.get("Name").and_then(Value::as_str).unwrap_or("").trim().to_string();
        if name.is_empty() {
            continue;
        }
        let status = item.get("ConnectionStatus").and_then(Value::as_str).unwrap_or("Disconnected").to_string();
        let credential = vpn_credential_read(&name).ok().flatten();
        let credential_saved = credential.is_some();
        let saved_username = credential.map(|value| value.username).unwrap_or_default();
        connections.push(json!({
            "name": name,
            "server": item.get("ServerAddress").and_then(Value::as_str).unwrap_or(""),
            "type": item.get("TunnelType").and_then(Value::as_str).unwrap_or(""),
            "status": status,
            "connected": status.eq_ignore_ascii_case("connected"),
            "remember_credential": item.get("RememberCredential").and_then(Value::as_bool).unwrap_or(false),
            "all_user": item.get("AllUserConnection").and_then(Value::as_bool).unwrap_or(false),
            "credential_saved": credential_saved,
            "saved_username": saved_username,
        }));
    }
    connections.sort_by(|a, b| {
        let ac = a.get("connected").and_then(Value::as_bool).unwrap_or(false);
        let bc = b.get("connected").and_then(Value::as_bool).unwrap_or(false);
        bc.cmp(&ac).then_with(|| {
            let an = a.get("name").and_then(Value::as_str).unwrap_or("").to_ascii_lowercase();
            let bn = b.get("name").and_then(Value::as_str).unwrap_or("").to_ascii_lowercase();
            an.cmp(&bn)
        })
    });
    Ok((connections, json!({
        "allow_metered": allow_metered,
        "allow_roaming": allow_roaming,
    })))
}

fn vpn_profile(name: &str) -> Result<Option<Value>, String> {
    let wanted = name.trim().to_ascii_lowercase();
    Ok(vpn_snapshot()?.0.into_iter().find(|item| {
        item.get("name")
            .and_then(Value::as_str)
            .map(|value| value.to_ascii_lowercase() == wanted)
            .unwrap_or(false)
    }))
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
        "network_mode": s.store.data.network_mode.clone(),
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

fn proxy_history_delay(proxy: &Value) -> Option<(String, u64)> {
    let item = proxy.get("history")?.as_array()?.last()?;
    let delay = item.get("delay")?.as_u64()?;
    let time = item.get("time").and_then(Value::as_str).unwrap_or("").to_string();
    Some((time, delay))
}

fn proxy_last_delay_info(proxy: &Value) -> Option<(String, u64)> {
    let mut candidates = Vec::new();
    if let Some(item) = proxy_history_delay(proxy) {
        candidates.push(item);
    }
    if let Some(extra) = proxy.get("extra").and_then(Value::as_object) {
        for value in extra.values() {
            if let Some(item) = proxy_history_delay(value) {
                candidates.push(item);
            }
        }
    }
    candidates.into_iter().max_by(|a, b| a.0.cmp(&b.0))
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
                        let proxy = proxies.get(n);
                        let nt = proxy.and_then(|x| x.get("type")).and_then(|v| v.as_str()).unwrap_or("");
                        let delay_info = proxy.and_then(proxy_last_delay_info);
                        json!({
                            "name": n,
                            "type": nt,
                            "delay": delay_info.as_ref().map(|item| item.1),
                            "delay_updated_at": delay_info.map(|item| item.0).unwrap_or_default(),
                        })
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
pub fn test_node_delay(state: State<'_, Shared>, name: String) -> Value {
    let name = name.trim().to_string();
    if name.is_empty() {
        return err("找不到該節點");
    }
    let port = { state.lock().unwrap().store.data.controller_port };
    let path = format!(
        "/proxies/{}/delay?timeout=5000&url={}",
        urlencoding::encode(&name),
        urlencoding::encode(TEST_URL)
    );
    match core::api("GET", port, &path, None, 12) {
        Ok(d) => json!({"ok": true, "name": name, "delay": d.get("delay").and_then(Value::as_u64).unwrap_or(0)}),
        Err(e) => err(e),
    }
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
    let port = { state.lock().unwrap().store.data.controller_port };
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
        "asset": update_asset(&release, install_mode() == "portable"),
        "install_mode": install_mode(),
    })
}

fn set_update_download_progress(
    progress: Option<&UpdateDownloadState>,
    phase: &str,
    received: u64,
    total: u64,
    path: Option<&Path>,
    error: Option<&str>,
) {
    let Some(progress) = progress else {
        return;
    };
    let active = matches!(phase, "downloading" | "verifying");
    let percent = if total > 0 {
        ((received.min(total) as f64 / total as f64) * 100.0).round() as u64
    } else {
        0
    };
    progress.update(json!({
        "active": active,
        "phase": phase,
        "received": received,
        "total": total,
        "percent": percent,
        "path": path.map(|v| v.to_string_lossy().to_string()),
        "error": error
    }));
}

fn download_update(
    url: &str,
    filename: &str,
    checksum_url: &str,
    progress: Option<&UpdateDownloadState>,
) -> Result<PathBuf, String> {
    let safe_name = Path::new(filename)
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or_else(|| "更新檔名無效".to_string())?;
    if safe_name != filename || update_asset_score(safe_name, std::env::consts::OS, false).is_none() {
        return Err("更新檔名或平台不相符".to_string());
    }
    if !safe_update_url(url) || !safe_update_url(checksum_url) {
        return Err("不安全的更新下載網址".to_string());
    }
    let folder = dirs::download_dir()
        .or_else(|| dirs::home_dir().map(|p| p.join("Downloads")))
        .unwrap_or_else(data_dir);
    fs::create_dir_all(&folder).map_err(|e| format!("無法建立下載資料夾：{e}"))?;
    let destination = folder.join(safe_name);
    let partial = folder.join(format!("{safe_name}.part"));
    set_update_download_progress(progress, "verifying", 0, 0, None, None);

    let sums = ureq::get(checksum_url)
        .set("User-Agent", SUB_UA)
        .timeout(Duration::from_secs(30))
        .call()
        .map_err(|e| format!("下載校驗檔失敗：{e}"))?
        .into_string()
        .map_err(|e| format!("讀取校驗檔失敗：{e}"))?;
    let expected = parse_sha256sums(&sums, safe_name).ok_or_else(|| "找不到更新檔的 SHA256 校驗值".to_string())?;

    let response = ureq::get(url)
        .set("User-Agent", SUB_UA)
        .timeout(Duration::from_secs(120))
        .call()
        .map_err(|e| format!("下載更新失敗：{e}"))?;
    let status = response.status();
    if !(200..300).contains(&status) {
        return Err(format!("更新伺服器回應 HTTP {status}"));
    }
    let total = response
        .header("Content-Length")
        .and_then(|v| v.parse::<u64>().ok())
        .ok_or_else(|| "更新檔缺少有效的 Content-Length".to_string())?;
    if total == 0 || total > 700 * 1024 * 1024 {
        return Err("更新檔大小無效或超過安全上限".to_string());
    }
    let mut reader = response.into_reader();
    let mut file = File::create(&partial).map_err(|e| format!("建立更新檔失敗：{e}"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 262144];
    let mut written = 0u64;
    let mut last_progress = Instant::now();
    set_update_download_progress(progress, "downloading", 0, total, None, None);
    let result = (|| -> Result<(), String> {
        loop {
            if progress.map(|state| state.cancel.load(Ordering::SeqCst)).unwrap_or(false) {
                return Err("更新下載已取消".to_string());
            }
            let read = reader.read(&mut buffer).map_err(|e| format!("讀取更新失敗：{e}"))?;
            if read == 0 {
                break;
            }
            written += read as u64;
            if written > total {
                return Err("更新檔大小超出宣告值".to_string());
            }
            hasher.update(&buffer[..read]);
            file.write_all(&buffer[..read]).map_err(|e| format!("寫入更新失敗：{e}"))?;
            if written == total || last_progress.elapsed() >= Duration::from_millis(120) {
                set_update_download_progress(progress, "downloading", written, total, None, None);
                last_progress = Instant::now();
            }
        }
        file.sync_all().map_err(|e| format!("同步更新檔失敗：{e}"))?;
        if written != total {
            return Err("更新檔下載不完整".to_string());
        }
        set_update_download_progress(progress, "verifying", written, total, None, None);
        let actual = format!("{:x}", hasher.finalize());
        if actual != expected {
            return Err("更新檔 SHA256 校驗失敗".to_string());
        }
        fs::rename(&partial, &destination).map_err(|e| format!("儲存更新檔失敗：{e}"))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&partial);
    }
    result?;
    set_update_download_progress(progress, "complete", written, total, Some(&destination), None);
    Ok(destination)
}

fn open_update_installer(path: &str) -> Result<(), String> {
    let target = fs::canonicalize(path).map_err(|e| format!("找不到更新安裝檔：{e}"))?;
    let downloads = dirs::download_dir()
        .or_else(|| dirs::home_dir().map(|p| p.join("Downloads")))
        .unwrap_or_else(data_dir);
    let downloads = fs::canonicalize(downloads).map_err(|e| format!("找不到下載資料夾：{e}"))?;
    if target.parent() != Some(downloads.as_path()) || !target.is_file() {
        return Err("更新安裝檔位置不安全或不存在".to_string());
    }
    let extension = target.extension().and_then(|v| v.to_str()).unwrap_or("").to_ascii_lowercase();
    let valid = match std::env::consts::OS {
        "windows" => extension == "exe",
        "macos" => extension == "dmg",
        "linux" => extension == "appimage" || extension == "deb",
        _ => false,
    };
    if !valid {
        return Err("不支援的更新安裝檔格式".to_string());
    }
    open::that(&target).map_err(|e| format!("啟動更新安裝檔失敗：{e}"))
}

#[tauri::command]
pub fn install_update(url: String, filename: String, sha256_url: String) -> Value {
    match download_update(&url, &filename, &sha256_url, None) {
        Ok(path) => json!({"ok": true, "path": path.to_string_lossy()}),
        Err(e) => err(e),
    }
}

#[tauri::command]
pub fn start_update_download(
    state: State<'_, Shared>,
    url: String,
    filename: String,
    sha256_url: String,
) -> Value {
    let download = {
        let s = state.lock().unwrap();
        s.update_download.clone()
    };
    let current = download.snapshot();
    if current.get("active").and_then(Value::as_bool).unwrap_or(false) {
        return err("已有更新正在下載");
    }
    download.cancel.store(false, Ordering::SeqCst);
    set_update_download_progress(Some(&download), "verifying", 0, 0, None, None);
    let initial_status = download.snapshot();
    let worker = download.clone();
    std::thread::spawn(move || {
        match download_update(&url, &filename, &sha256_url, Some(&worker)) {
            Ok(_) => {}
            Err(e) => {
                let phase = if worker.cancel.load(Ordering::SeqCst) {
                    "cancelled"
                } else {
                    "error"
                };
                set_update_download_progress(Some(&worker), phase, 0, 0, None, Some(&e));
            }
        }
    });
    json!({"ok": true, "started": true, "status": initial_status})
}

#[tauri::command]
pub fn update_download_status(state: State<'_, Shared>) -> Value {
    let download = {
        let s = state.lock().unwrap();
        s.update_download.clone()
    };
    json!({"ok": true, "status": download.snapshot()})
}

#[tauri::command]
pub fn cancel_update_download(state: State<'_, Shared>) -> Value {
    let download = {
        let s = state.lock().unwrap();
        s.update_download.clone()
    };
    let current = download.snapshot();
    if !current.get("active").and_then(Value::as_bool).unwrap_or(false) {
        return json!({"ok": true, "cancelled": false});
    }
    download.cancel.store(true, Ordering::SeqCst);
    json!({"ok": true, "cancelled": true})
}

fn version_key(value: &str) -> Vec<u64> {
    let mut key = regex::Regex::new(r"\d+")
        .unwrap()
        .find_iter(value)
        .map(|m| m.as_str().parse::<u64>().unwrap_or(0))
        .collect::<Vec<_>>();
    key.resize(4, 0);
    key
}

fn version_at_least(current: &str, target: &str) -> bool {
    if target.trim().is_empty() {
        return false;
    }
    version_key(current) >= version_key(target)
}

fn updates_dir() -> PathBuf {
    data_dir().join("updates")
}

fn update_state_path() -> PathBuf {
    updates_dir().join("state.json")
}

fn previous_backup_dir() -> PathBuf {
    updates_dir().join("previous")
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| format!("建立更新備份資料夾失敗：{e}"))?;
    for entry in fs::read_dir(src).map_err(|e| format!("讀取目前安裝資料夾失敗：{e}"))? {
        let entry = entry.map_err(|e| format!("讀取安裝檔案失敗：{e}"))?;
        let file_type = entry.file_type().map_err(|e| format!("讀取檔案類型失敗：{e}"))?;
        let target = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_recursive(&entry.path(), &target)?;
        } else if file_type.is_file() {
            fs::copy(entry.path(), target).map_err(|e| format!("複製安裝檔案失敗：{e}"))?;
        }
    }
    Ok(())
}

fn create_update_backup(target_version: &str) -> Result<Value, String> {
    let exe = std::env::current_exe().map_err(|e| format!("找不到目前程式路徑：{e}"))?;
    let app_dir = exe
        .parent()
        .ok_or_else(|| "找不到目前安裝資料夾".to_string())?;
    let backup = previous_backup_dir();
    if backup.exists() {
        fs::remove_dir_all(&backup).map_err(|e| format!("清理舊版備份失敗：{e}"))?;
    }
    fs::create_dir_all(updates_dir()).map_err(|e| format!("建立更新資料夾失敗：{e}"))?;
    copy_dir_recursive(app_dir, &backup)?;
    let state = json!({
        "pending": true,
        "completed": false,
        "failed": false,
        "from_version": APP_VERSION,
        "target_version": target_version,
        "backup_dir": backup.to_string_lossy(),
        "install_dir": app_dir.to_string_lossy(),
        "executable": exe.to_string_lossy(),
        "install_mode": install_mode(),
        "created_at": chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
    });
    fs::write(update_state_path(), serde_json::to_string_pretty(&state).map_err(|e| e.to_string())?)
        .map_err(|e| format!("寫入更新狀態失敗：{e}"))?;
    Ok(state)
}

fn read_update_state() -> Value {
    fs::read_to_string(update_state_path())
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .unwrap_or_else(|| json!({}))
}

#[tauri::command]
pub fn get_update_state() -> Value {
    let mut state = read_update_state();
    let target = state.get("target_version").and_then(Value::as_str).unwrap_or("").to_string();
    let pending = state.get("pending").and_then(Value::as_bool).unwrap_or(false);
    if pending && version_at_least(APP_VERSION, &target) {
        state["pending"] = json!(false);
        state["completed"] = json!(true);
        let _ = fs::write(update_state_path(), serde_json::to_string_pretty(&state).unwrap_or_default());
    }
    let pending_now = state.get("pending").and_then(Value::as_bool).unwrap_or(false);
    let backup = previous_backup_dir();
    json!({
        "ok": true,
        "current_version": APP_VERSION,
        "install_mode": install_mode(),
        "backup_available": backup.is_dir(),
        "previous_version": state.get("from_version").and_then(Value::as_str).unwrap_or(""),
        "target_version": target,
        "pending": pending_now,
        "failed": pending_now && !version_at_least(APP_VERSION, &target),
        "completed": state.get("completed").and_then(Value::as_bool).unwrap_or(false),
        "created_at": state.get("created_at").and_then(Value::as_str).unwrap_or(""),
        "backup_dir": backup.to_string_lossy()
    })
}

const UPDATE_HELPER_SCRIPT: &str = r#"param(
  [Parameter(Mandatory=$true)][ValidateSet('portable','rollback')][string]$Action,
  [string]$Archive = '',
  [Parameter(Mandatory=$true)][string]$AppDir,
  [Parameter(Mandatory=$true)][string]$Exe,
  [Parameter(Mandatory=$true)][string]$Backup
)
$ErrorActionPreference = 'Stop'
$updateRoot = Split-Path -Parent $Backup
$logPath = Join-Path $updateRoot 'apply-update.log'
Start-Transcript -Path $logPath -Append | Out-Null
function Wait-KumoRouteExit {
  for ($i = 0; $i -lt 80; $i++) {
    try {
      $stream = [System.IO.File]::Open($Exe, 'Open', 'ReadWrite', 'None')
      $stream.Close()
      return
    } catch { Start-Sleep -Milliseconds 500 }
  }
  throw 'KumoRoute 程式檔仍在執行，無法完成更新。'
}
function Restore-Backup {
  if (Test-Path -LiteralPath $Backup) {
    Copy-Item -Path (Join-Path $Backup '*') -Destination $AppDir -Recurse -Force
    Start-Process -FilePath $Exe -WorkingDirectory $AppDir
  }
}
try {
  Start-Sleep -Milliseconds 1200
  Wait-KumoRouteExit
  if ($Action -eq 'portable') {
    $temp = Join-Path $env:TEMP ('KumoRoute-update-' + [guid]::NewGuid().ToString('N'))
    try {
      Expand-Archive -LiteralPath $Archive -DestinationPath $temp -Force
      $source = Join-Path $temp 'KumoRoute'
      if (-not (Test-Path -LiteralPath (Join-Path $source 'KumoRoute.exe'))) { throw '更新 ZIP 內容不完整。' }
      Copy-Item -Path (Join-Path $source '*') -Destination $AppDir -Recurse -Force
    } finally {
      if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
    }
  } else {
    Copy-Item -Path (Join-Path $Backup '*') -Destination $AppDir -Recurse -Force
  }
  Start-Process -FilePath $Exe -WorkingDirectory $AppDir
} catch {
  ($_ | Out-String) | Add-Content -LiteralPath $logPath
  Restore-Backup
  exit 1
} finally {
  Stop-Transcript | Out-Null
}
"#;

fn write_update_helper() -> Result<PathBuf, String> {
    let path = updates_dir().join("apply-update.ps1");
    fs::create_dir_all(updates_dir()).map_err(|e| format!("建立更新資料夾失敗：{e}"))?;
    fs::write(&path, UPDATE_HELPER_SCRIPT).map_err(|e| format!("寫入更新輔助程式失敗：{e}"))?;
    Ok(path)
}

#[cfg(windows)]
fn launch_update_helper(action: &str, archive: &str, app_dir: &str, exe: &str, backup: &str) -> Result<(), String> {
    let script = write_update_helper()?;
    hidden_command("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script.to_string_lossy().as_ref(),
            "-Action",
            action,
            "-Archive",
            archive,
            "-AppDir",
            app_dir,
            "-Exe",
            exe,
            "-Backup",
            backup,
        ])
        .spawn()
        .map_err(|e| format!("啟動更新輔助程式失敗：{e}"))?;
    Ok(())
}

#[cfg(not(windows))]
fn launch_update_helper(_action: &str, _archive: &str, _app_dir: &str, _exe: &str, _backup: &str) -> Result<(), String> {
    Err("此平台不支援背景更新輔助程式".to_string())
}

#[tauri::command]
pub fn rollback_update(app: tauri::AppHandle) -> Value {
    let state = read_update_state();
    let backup = previous_backup_dir();
    if !backup.is_dir() {
        return err("找不到上一版備份");
    }
    let app_dir = state.get("install_dir").and_then(Value::as_str).unwrap_or("");
    let exe = state.get("executable").and_then(Value::as_str).unwrap_or("");
    if app_dir.is_empty() || exe.is_empty() {
        return err("更新備份資訊不完整");
    }
    if let Err(e) = launch_update_helper("rollback", "", app_dir, exe, &backup.to_string_lossy().to_string()) {
        return err(e);
    }
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(800));
        app.exit(0);
    });
    json!({"ok": true, "rollback_started": true})
}

#[tauri::command]
pub fn run_update_installer(app: tauri::AppHandle, path: String, target_version: String) -> Value {
    let target = match fs::canonicalize(&path) {
        Ok(path) => path,
        Err(e) => return err(format!("找不到更新安裝檔：{e}")),
    };
    let extension = target.extension().and_then(|v| v.to_str()).unwrap_or("").to_ascii_lowercase();
    if extension == "zip" {
        if install_mode() != "portable" {
            return err("ZIP 更新只適用於免安裝版");
        }
        let backup = match create_update_backup(&target_version) {
            Ok(value) => value,
            Err(e) => return err(e),
        };
        let backup_path = backup.get("backup_dir").and_then(Value::as_str).unwrap_or("");
        let app_dir = backup.get("install_dir").and_then(Value::as_str).unwrap_or("");
        let exe = backup.get("executable").and_then(Value::as_str).unwrap_or("");
        if let Err(e) = launch_update_helper("portable", &target.to_string_lossy(), app_dir, exe, backup_path) {
            return err(e);
        }
    } else {
        if let Err(e) = create_update_backup(&target_version) {
            return err(e);
        }
        if let Err(e) = open_update_installer(&path) {
            return err(e);
        }
    }
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(800));
        app.exit(0);
    });
    ok()
}

#[tauri::command]
pub fn vpn_list(state: State<'_, Shared>) -> Value {
    let (disable_system_proxy, restore_system_proxy, network_mode) = {
        let s = state.lock().unwrap();
        (s.store.data.vpn_disable_system_proxy, s.store.data.vpn_restore_system_proxy, s.store.data.network_mode.clone())
    };
    if std::env::consts::OS != "windows" {
        return json!({
            "ok": true,
            "supported": false,
            "connections": [],
            "advanced": {"allow_metered": true, "allow_roaming": true},
            "settings": {
                "disable_system_proxy": disable_system_proxy,
                "restore_system_proxy": restore_system_proxy,
                "network_mode": network_mode
            }
        });
    }
    match vpn_snapshot() {
        Ok((connections, advanced)) => json!({
            "ok": true,
            "supported": true,
            "connections": connections,
            "advanced": advanced,
            "settings": {
                "disable_system_proxy": disable_system_proxy,
                "restore_system_proxy": restore_system_proxy,
                "network_mode": network_mode
            }
        }),
        Err(e) => json!({
            "ok": false,
            "supported": true,
            "connections": [],
            "advanced": {"allow_metered": true, "allow_roaming": true},
            "settings": {
                "disable_system_proxy": disable_system_proxy,
                "restore_system_proxy": restore_system_proxy,
                "network_mode": network_mode
            },
            "error": e
        }),
    }
}

#[tauri::command]
pub fn vpn_connect(state: State<'_, Shared>, name: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let profile = match vpn_profile(&name) {
        Ok(Some(profile)) => profile,
        Ok(None) => return err("找不到該 VPN 連線"),
        Err(e) => return err(e),
    };
    let Some(profile_name) = profile.get("name").and_then(Value::as_str) else {
        return err("VPN 連線名稱無效");
    };
    let credential = match vpn_credential_read(profile_name) {
        Ok(Some(value)) => value,
        Ok(None) => {
            return json!({
                "ok": false,
                "needs_credentials": true,
                "username": profile.get("saved_username").and_then(Value::as_str).unwrap_or("")
            });
        }
        Err(e) => return err(e),
    };
    let proxy_disabled = match prepare_vpn_proxy(&mut state.lock().unwrap()) {
        Ok(value) => value,
        Err(e) => return err(format!("關閉系統代理失敗：{e}")),
    };
    match vpn_ras_dial(profile_name, &credential.username, &credential.password) {
        Ok(()) => json!({"ok": true, "connected": true, "proxy_disabled": proxy_disabled}),
        Err((code, _)) if code == 645 || code == 691 => {
            restore_vpn_proxy(&mut state.lock().unwrap());
            vpn_credential_delete(profile_name);
            json!({
                "ok": false,
                "needs_credentials": true,
                "stale_credentials": true,
                "username": credential.username
            })
        }
        Err((code, message)) => {
            restore_vpn_proxy(&mut state.lock().unwrap());
            json!({"ok": false, "error": message, "code": code})
        }
    }
}

#[tauri::command]
pub fn vpn_connect_with_credentials(
    state: State<'_, Shared>,
    name: String,
    username: String,
    password: String,
    remember: bool,
) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let profile = match vpn_profile(&name) {
        Ok(Some(profile)) => profile,
        Ok(None) => return err("找不到該 VPN 連線"),
        Err(e) => return err(e),
    };
    let Some(profile_name) = profile.get("name").and_then(Value::as_str) else {
        return err("VPN 連線名稱無效");
    };
    let username = username.trim().to_string();
    if username.is_empty() || password.is_empty() {
        return err("請輸入 VPN 使用者名稱與密碼");
    }
    let proxy_disabled = match prepare_vpn_proxy(&mut state.lock().unwrap()) {
        Ok(value) => value,
        Err(e) => return err(format!("關閉系統代理失敗：{e}")),
    };
    match vpn_ras_dial(profile_name, &username, &password) {
        Ok(()) => {
            if remember {
                if let Err(e) = vpn_credential_write(profile_name, &username, &password) {
                    return json!({
                        "ok": true,
                        "connected": true,
                        "credentials_saved": false,
                        "warning": format!("已連線，但{e}")
                    });
                }
            } else {
                vpn_credential_delete(profile_name);
            }
            json!({
                "ok": true,
                "connected": true,
                "credentials_saved": remember,
                "proxy_disabled": proxy_disabled
            })
        }
        Err((code, message)) => {
            restore_vpn_proxy(&mut state.lock().unwrap());
            json!({"ok": false, "error": message, "code": code})
        }
    }
}

#[tauri::command]
pub fn vpn_disconnect(state: State<'_, Shared>, name: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let profile = match vpn_profile(&name) {
        Ok(Some(profile)) => profile,
        Ok(None) => return err("找不到該 VPN 連線"),
        Err(e) => return err(e),
    };
    let Some(profile_name) = profile.get("name").and_then(Value::as_str) else {
        return err("VPN 連線名稱無效");
    };
    match hidden_command("rasdial.exe").args([profile_name, "/disconnect"]).output() {
        Ok(output) if output.status.success() => {
            let restored = restore_vpn_proxy(&mut state.lock().unwrap());
            json!({"ok": true, "disconnected": true, "proxy_restored": restored})
        }
        Ok(output) => err(format!("VPN 斷線失敗（代碼 {}）", output.status.code().unwrap_or(-1))),
        Err(e) => err(format!("VPN 斷線失敗：{e}")),
    }
}

#[tauri::command]
pub fn vpn_set_auto_proxy(state: State<'_, Shared>, enabled: bool) -> Value {
    let mut s = state.lock().unwrap();
    s.store.data.vpn_disable_system_proxy = enabled;
    match s.store.save() {
        Ok(_) => json!({"ok": true, "disable_system_proxy": enabled}),
        Err(e) => err(format!("保存 VPN 設定失敗：{e}")),
    }
}

#[tauri::command]
pub fn vpn_add(name: String, server: String, tunnel_type: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let name = name.trim().to_string();
    let server = server.trim().to_string();
    let Some(tunnel) = vpn_tunnel(&tunnel_type) else {
        return err("請輸入 VPN 名稱、伺服器與類型");
    };
    if name.is_empty() || server.is_empty() {
        return err("請輸入 VPN 名稱、伺服器與類型");
    }
    if matches!(vpn_profile(&name), Ok(Some(_))) {
        return err("已存在同名 VPN 連線");
    }
    let auth = if tunnel == "Pptp" || tunnel == "L2tp" { "MsChapv2" } else { "Eap" };
    let script = format!(
        "Add-VpnConnection -Name {} -ServerAddress {} -TunnelType {} -EncryptionLevel Required -AuthenticationMethod {} -RememberCredential -Force",
        ps_quote(&name), ps_quote(&server), ps_quote(tunnel), ps_quote(auth)
    );
    match vpn_profile_command(&script) {
        Ok(()) => json!({"ok": true, "name": name}),
        Err(e) => err(format!("新增 VPN 失敗：{e}")),
    }
}

#[tauri::command]
pub fn vpn_edit(name: String, server: String, tunnel_type: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let name = name.trim().to_string();
    let server = server.trim().to_string();
    let Some(tunnel) = vpn_tunnel(&tunnel_type) else {
        return err("請輸入 VPN 名稱、伺服器與類型");
    };
    if name.is_empty() || server.is_empty() {
        return err("請輸入 VPN 名稱、伺服器與類型");
    }
    let script = format!(
        "Set-VpnConnection -Name {} -ServerAddress {} -TunnelType {} -RememberCredential $true",
        ps_quote(&name), ps_quote(&server), ps_quote(tunnel)
    );
    match vpn_profile_command(&script) {
        Ok(()) => ok(),
        Err(e) => err(format!("修改 VPN 失敗：{e}")),
    }
}

#[tauri::command]
pub fn vpn_delete(name: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let name = name.trim().to_string();
    if name.is_empty() {
        return err("找不到該 VPN 連線");
    }
    let script = format!("Remove-VpnConnection -Name {} -Force", ps_quote(&name));
    match vpn_profile_command(&script) {
        Ok(()) => {
            vpn_credential_delete(&name);
            ok()
        }
        Err(e) => err(format!("刪除 VPN 失敗：{e}")),
    }
}

#[tauri::command]
pub fn vpn_set_restore_proxy(state: State<'_, Shared>, enabled: bool) -> Value {
    let mut s = state.lock().unwrap();
    s.store.data.vpn_restore_system_proxy = enabled;
    match s.store.save() {
        Ok(_) => json!({"ok": true, "restore_system_proxy": enabled}),
        Err(e) => err(format!("保存 VPN 設定失敗：{e}")),
    }
}

#[tauri::command]
pub fn set_network_mode(state: State<'_, Shared>, mode: String) -> Value {
    if !["proxy", "vpn", "coexist"].contains(&mode.as_str()) {
        return err("無效的網路接管模式");
    }
    let connected = if mode == "proxy" && std::env::consts::OS == "windows" {
        match vpn_snapshot() {
            Ok((connections, _)) => connections
                .into_iter()
                .filter(|item| item.get("connected").and_then(Value::as_bool).unwrap_or(false))
                .collect::<Vec<_>>(),
            Err(e) => return err(format!("無法讀取 VPN 連線：{e}")),
        }
    } else {
        Vec::new()
    };
    let mut s = state.lock().unwrap();
    let port = s.store.data.controller_port;
    if mode == "vpn" && proxy::is_on(&s.store) {
        if let Err(e) = proxy::set_system_proxy(&mut s.store, false, core::is_up(port)) {
            return err(e);
        }
    } else if mode == "proxy" {
        let mut failures = Vec::new();
        for item in connected {
            let Some(name) = item.get("name").and_then(Value::as_str) else {
                continue;
            };
            match hidden_command("rasdial.exe").args([name, "/disconnect"]).output() {
                Ok(output) if output.status.success() => {}
                Ok(output) => failures.push(format!("{name}：代碼 {}", output.status.code().unwrap_or(-1))),
                Err(e) => failures.push(format!("{name}：{e}")),
            }
        }
        if !failures.is_empty() {
            return err(format!("無法切換到只用代理：{}", failures.join("；")));
        }
        if !proxy::is_on(&s.store) {
            if let Err(e) = proxy::set_system_proxy(&mut s.store, true, core::is_up(port)) {
                return err(e);
            }
        }
    }
    s.store.data.network_mode = mode.clone();
    if let Err(e) = s.store.save() {
        return err(format!("保存網路模式失敗：{e}"));
    }
    json!({"ok": true, "network_mode": mode})
}

#[tauri::command]
pub fn network_diagnostics(state: State<'_, Shared>) -> Value {
    let (proxy_on, network_mode) = {
        let s = state.lock().unwrap();
        (proxy::is_on(&s.store), s.store.data.network_mode.clone())
    };
    let dns_servers = system_dns_servers();
    let addresses = "cp.cloudflare.com:443".to_socket_addrs().map(|v| v.collect::<Vec<_>>()).unwrap_or_default();
    let (config_doh, dot_templates) = configured_dns_protocols();
    let system_doh = doh_template_count();
    let doh_templates = system_doh.saturating_add(config_doh);
    let ipv6_route = Profiles::ipv6_route_available();
    let ipv6_connectivity = test_ipv6_connectivity();
    let ipv6_preferred = addresses.first().map(|a| a.is_ipv6()).unwrap_or(false);
    let dns_ok = !addresses.is_empty();
    let dns_leak_suspected = proxy_on && !dns_servers.is_empty() && !dns_servers.iter().any(|v| v.starts_with("127.") || v == "::1");
    let dns_encryption_conflict = (system_doh > 0 || config_doh > 0) && dot_templates > 0;
    let mut issues = grouped_network_issues(&core::log_lines(300));
    if ipv6_route && !ipv6_connectivity {
        merge_network_issue(&mut issues, "ipv6", 1, "IPv6 已有路由，但實際連線失敗");
    }
    if !dns_ok {
        merge_network_issue(&mut issues, "dns", 1, "DNS 查詢失敗");
    }
    if dns_leak_suspected {
        merge_network_issue(&mut issues, "dns-leak", 1, "系統代理開啟，但系統 DNS 不是本機位址");
    }
    if ipv6_preferred && !ipv6_connectivity {
        merge_network_issue(&mut issues, "ipv6-preference", 1, "DNS 優先回傳 IPv6，但 IPv6 無法連線");
    }
    if dns_encryption_conflict {
        merge_network_issue(&mut issues, "dns-encrypted", 1, "同時偵測到 DoH 與 DoT 設定，可能造成解析衝突");
    }
    json!({
        "ok": true,
        "ipv6_route": ipv6_route,
        "ipv6_connectivity": ipv6_connectivity,
        "ipv6_preferred": ipv6_preferred,
        "dns_ok": dns_ok,
        "dns_servers": dns_servers,
        "system_doh_templates": system_doh,
        "config_doh_templates": config_doh,
        "doh_templates": doh_templates,
        "dot_templates": dot_templates,
        "dns_encryption_conflict": dns_encryption_conflict,
        "dns_leak_suspected": dns_leak_suspected,
        "proxy_on": proxy_on,
        "network_mode": network_mode,
        "issues": issues,
    })
}

#[tauri::command]
pub fn network_repair(state: State<'_, Shared>, action: String) -> Value {
    let action = action.trim().to_ascii_lowercase();
    let mut s = state.lock().unwrap();
    let previous_ipv6 = s.store.data.force_disable_ipv6;
    let previous_dns = s.store.data.dns_mode.clone();
    match action.as_str() {
        "ipv6" => s.store.data.force_disable_ipv6 = true,
        "dns" => s.store.data.dns_mode = "backup".into(),
        "dns-system" => s.store.data.dns_mode = "auto".into(),
        "flush" => {
            let _ = hidden_command("ipconfig.exe").arg("/flushdns").output();
            return json!({"ok": true, "action": action});
        }
        _ => return err("無效的網路修復動作"),
    }
    if let Err(e) = s.store.save() {
        s.store.data.force_disable_ipv6 = previous_ipv6;
        s.store.data.dns_mode = previous_dns;
        return err(format!("保存網路修復設定失敗：{e}"));
    }
    if let Err(e) = do_reload(&mut *s) {
        s.store.data.force_disable_ipv6 = previous_ipv6;
        s.store.data.dns_mode = previous_dns;
        let _ = s.store.save();
        return err(e);
    }
    json!({"ok": true, "action": action})
}

#[tauri::command]
pub fn vpn_forget_credentials(name: String) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    vpn_credential_delete(name.trim());
    ok()
}

#[tauri::command]
pub fn vpn_open_settings() -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    match open::that("ms-settings:network-vpn") {
        Ok(_) => ok(),
        Err(e) => err(format!("無法開啟 Windows VPN 設定：{e}")),
    }
}

#[tauri::command]
pub fn vpn_set_advanced(setting: String, enabled: bool) -> Value {
    if std::env::consts::OS != "windows" {
        return err("Windows VPN 僅支援 Windows");
    }
    let value_name = match setting.trim().to_ascii_lowercase().as_str() {
        "metered" => "NoCostedNetwork",
        "roaming" => "NoRoamingNetwork",
        _ => return err("無效的 VPN 進階設定"),
    };
    let data = if enabled { "0" } else { "1" };
    let direct = hidden_command("reg.exe")
        .args([
            "add", VPN_REGISTRY_KEY,
            "/v", value_name, "/t", "REG_DWORD", "/d", data, "/f",
        ])
        .output();
    if matches!(&direct, Ok(output) if output.status.success()) {
        return json!({"ok": true, "pending": false});
    }
    let script = format!(
        "Start-Process -FilePath 'reg.exe' -Verb RunAs -WindowStyle Hidden -Wait \
         -ArgumentList @('add','{}','/v','{}','/t','REG_DWORD','/d','{}','/f')",
        VPN_REGISTRY_KEY, value_name, data
    );
    match hidden_command("powershell.exe")
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script.as_str()])
        .spawn()
    {
        Ok(_) => json!({
            "ok": true,
            "pending": true,
            "message": "請在 Windows 的 UAC 提示中允許變更。"
        }),
        Err(e) => err(format!("更新 VPN 進階設定失敗：{e}")),
    }
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


#[cfg(all(test, windows))]
mod vpn_credential_tests {
    use super::*;

    #[test]
    fn credential_manager_roundtrip() {
        let name = format!("__test_{}", uuid::Uuid::new_v4());
        vpn_credential_write(&name, "test-user", "test-password").unwrap();
        let credential = vpn_credential_read(&name).unwrap().expect("credential");
        assert_eq!(credential.username, "test-user");
        assert_eq!(credential.password, "test-password");
        vpn_credential_delete(&name);
        assert!(vpn_credential_read(&name).unwrap().is_none());
    }
}


#[cfg(test)]
mod network_diagnostics_tests {
    use super::*;

    #[test]
    fn grouped_network_issues_are_merged_by_type() {
        let lines = vec![
            "IPv6 unreachable network".to_string(),
            "DNS lookup failed".to_string(),
            "DNS timeout".to_string(),
            "request timeout".to_string(),
        ];
        let mut issues = grouped_network_issues(&lines);
        merge_network_issue(&mut issues, "ipv6", 1, "IPv6 已有路由，但實際連線失敗");
        let ipv6 = issues.iter().find(|item| item["type"] == "ipv6").unwrap();
        assert_eq!(ipv6["count"], 2);
        assert_eq!(ipv6["message"], "IPv6 已有路由，但實際連線失敗");
        let dns = issues.iter().find(|item| item["type"] == "dns").unwrap();
        assert_eq!(dns["count"], 2);
    }

    #[test]
    fn encrypted_dns_protocols_are_counted() {
        let dns: serde_yaml::Value = serde_yaml::from_str(
            "nameserver: ['https://dns.example/query', 'tls://dot.example']\nfallback: ['quic://dns.example']",
        )
        .unwrap();
        let mut doh = 0;
        let mut dot = 0;
        collect_dns_protocols(&dns, &mut doh, &mut dot);
        assert_eq!(doh, 2);
        assert_eq!(dot, 1);
    }
}

#[cfg(test)]
mod update_tests {
    use super::*;

    fn release() -> Value {
        json!({
            "assets": [
                {"name": "KumoRoute-win-x64-setup.exe", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/KumoRoute-win-x64-setup.exe", "size": 23000000},
                {"name": "KumoRoute-win-x64.zip", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/KumoRoute-win-x64.zip", "size": 30000000},
                {"name": "KumoRoute-macos-universal.dmg", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/KumoRoute-macos-universal.dmg", "size": 54000000},
                {"name": "KumoRoute-linux-x86_64.AppImage", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/KumoRoute-linux-x86_64.AppImage", "size": 108000000},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/SHA256SUMS.txt", "size": 600}
            ]
        })
    }

    #[test]
    fn selects_asset_for_current_platform() {
        let asset = update_asset(&release(), false).expect("asset");
        let name = asset.get("filename").and_then(Value::as_str).unwrap_or("");
        match std::env::consts::OS {
            "windows" => assert_eq!(name, "KumoRoute-win-x64-setup.exe"),
            "macos" => assert_eq!(name, "KumoRoute-macos-universal.dmg"),
            "linux" => assert_eq!(name, "KumoRoute-linux-x86_64.AppImage"),
            _ => panic!("unexpected platform"),
        }
        assert!(asset.get("sha256_url").and_then(Value::as_str).unwrap_or("").ends_with("SHA256SUMS.txt"));
    }

    #[test]
    fn portable_build_prefers_zip() {
        if std::env::consts::OS != "windows" {
            return;
        }
        let asset = update_asset(&release(), true).expect("asset");
        assert_eq!(asset.get("filename").and_then(Value::as_str), Some("KumoRoute-win-x64.zip"));
    }

    #[test]
    fn parses_checksum_and_rejects_unsafe_urls() {
        let digest = "a".repeat(64);
        let sums = format!("{digest}  KumoRoute-win-x64-setup.exe\n");
        assert_eq!(parse_sha256sums(&sums, "KumoRoute-win-x64-setup.exe"), Some(digest));
        assert!(safe_update_url("https://github.com/cypwlp/kumoroute/releases/download/v0.7.6/file.exe"));
        assert!(!safe_update_url("https://evil.example/file.exe"));
        assert!(!safe_update_url("http://github.com/file.exe"));
    }
}
