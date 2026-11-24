use crate::state::{ProxySnapshot, Store};
use serde::Serialize;

pub const PROXY_OVERRIDE: &str = "<local>;localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*";

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn split_host_port(server: &str) -> (String, u16) {
    match server.rsplit_once(':') {
        Some((h, p)) => (h.to_string(), p.parse().unwrap_or(0)),
        None => (server.to_string(), 0),
    }
}

#[cfg(windows)]
mod imp {
    use std::ffi::c_void;

    use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE};
    use winreg::RegKey;

    use crate::state::ProxySnapshot;
    use windows::core::PWSTR;
    use windows::Win32::NetworkManagement::Rras::{RasEnumConnectionsW, RASCONNW};
    use windows::Win32::Networking::WinInet::{
        InternetQueryOptionW, InternetSetOptionW, INTERNET_OPTION_PER_CONNECTION_OPTION,
        INTERNET_OPTION_REFRESH, INTERNET_PER_CONN_FLAGS,
        INTERNET_PER_CONN_OPTIONW, INTERNET_PER_CONN_OPTIONW_0, INTERNET_PER_CONN_OPTION_LISTW,
        INTERNET_PER_CONN_PROXY_BYPASS, INTERNET_PER_CONN_PROXY_SERVER, PROXY_TYPE_DIRECT,
        PROXY_TYPE_PROXY,
    };

    const INTERNET_SETTINGS: &str = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings";

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// WinINET stores proxy settings per *connection*: the LAN entry plus one for
    /// every active RAS/VPN dial-up. Browsers follow whichever connection they
    /// route over, so looking at the LAN entry (or the registry values) alone
    /// misses the VPN case entirely.
    pub fn active_connections() -> Vec<Option<String>> {
        let mut list: Vec<Option<String>> = vec![None];
        let mut size: u32 = 0;
        let mut count: u32 = 0;
        unsafe {
            if RasEnumConnectionsW(None, &mut size, &mut count) == 0 && size > 0 {
                let entries = size as usize / std::mem::size_of::<RASCONNW>() + 1;
                let mut buffer: Vec<RASCONNW> = vec![RASCONNW::default(); entries];
                buffer[0].dwSize = std::mem::size_of::<RASCONNW>() as u32;
                let mut size = size;
                if RasEnumConnectionsW(Some(buffer.as_mut_ptr()), &mut size, &mut count) == 0 {
                    for entry in buffer.iter().take(count as usize) {
                        let name = entry.szEntryName;
                        let end = name.iter().position(|c| *c == 0).unwrap_or(name.len());
                        if let Ok(text) = String::from_utf16(&name[..end]) {
                            if !text.is_empty() {
                                list.push(Some(text));
                            }
                        }
                    }
                }
            }
        }
        list
    }

    pub fn query_flags(connection: Option<&str>) -> Option<u32> {
        let mut name = connection.map(wide);
        let mut option = INTERNET_PER_CONN_OPTIONW {
            dwOption: INTERNET_PER_CONN_FLAGS,
            Value: INTERNET_PER_CONN_OPTIONW_0 { dwValue: 0 },
        };
        let mut list = INTERNET_PER_CONN_OPTION_LISTW {
            dwSize: std::mem::size_of::<INTERNET_PER_CONN_OPTION_LISTW>() as u32,
            pszConnection: name
                .as_mut()
                .map(|value| PWSTR(value.as_mut_ptr()))
                .unwrap_or(PWSTR::null()),
            dwOptionCount: 1,
            dwOptionError: 0,
            pOptions: &mut option,
        };
        let mut size = std::mem::size_of::<INTERNET_PER_CONN_OPTION_LISTW>() as u32;
        unsafe {
            InternetQueryOptionW(
                None,
                INTERNET_OPTION_PER_CONNECTION_OPTION,
                Some(&mut list as *mut _ as *mut c_void),
                &mut size,
            )
            .ok()?;
            Some(option.Value.dwValue)
        }
    }

    pub fn set_options(connection: Option<&str>, proxied: bool, server: &str) -> Result<(), String> {
        let mut name = connection.map(wide);
        let mut server_text = wide(server);
        let mut bypass = wide(super::PROXY_OVERRIDE);
        let flags = if proxied {
            PROXY_TYPE_DIRECT | PROXY_TYPE_PROXY
        } else {
            PROXY_TYPE_DIRECT
        };
        let mut options = [
            INTERNET_PER_CONN_OPTIONW {
                dwOption: INTERNET_PER_CONN_FLAGS,
                Value: INTERNET_PER_CONN_OPTIONW_0 { dwValue: flags },
            },
            INTERNET_PER_CONN_OPTIONW {
                dwOption: INTERNET_PER_CONN_PROXY_SERVER,
                Value: INTERNET_PER_CONN_OPTIONW_0 {
                    pszValue: PWSTR(server_text.as_mut_ptr()),
                },
            },
            INTERNET_PER_CONN_OPTIONW {
                dwOption: INTERNET_PER_CONN_PROXY_BYPASS,
                Value: INTERNET_PER_CONN_OPTIONW_0 {
                    pszValue: PWSTR(bypass.as_mut_ptr()),
                },
            },
        ];
        let list = INTERNET_PER_CONN_OPTION_LISTW {
            dwSize: std::mem::size_of::<INTERNET_PER_CONN_OPTION_LISTW>() as u32,
            pszConnection: name
                .as_mut()
                .map(|value| PWSTR(value.as_mut_ptr()))
                .unwrap_or(PWSTR::null()),
            dwOptionCount: options.len() as u32,
            dwOptionError: 0,
            pOptions: options.as_mut_ptr(),
        };
        let size = std::mem::size_of::<INTERNET_PER_CONN_OPTION_LISTW>() as u32;
        unsafe {
            InternetSetOptionW(
                None,
                INTERNET_OPTION_PER_CONNECTION_OPTION,
                Some(&list as *const _ as *const c_void),
                size,
            )
            .map_err(|e| e.to_string())
        }
    }

    fn registry_snapshot() -> ProxySnapshot {
        let hkcu = RegKey::predef(HKEY_CURRENT_USER);
        let Ok(key) = hkcu.open_subkey_with_flags(INTERNET_SETTINGS, KEY_READ) else {
            return ProxySnapshot::default();
        };
        ProxySnapshot {
            enable: key.get_value("ProxyEnable").unwrap_or(0),
            server: key.get_value("ProxyServer").unwrap_or_default(),
            override_list: key.get_value("ProxyOverride").unwrap_or_default(),
        }
    }

    pub fn get_system_proxy() -> ProxySnapshot {
        let snap = registry_snapshot();
        let lan_proxied = query_flags(None)
            .map(|flags| flags & PROXY_TYPE_PROXY != 0)
            .unwrap_or(false);
        ProxySnapshot {
            enable: if lan_proxied || snap.enable == 1 { 1 } else { 0 },
            ..snap
        }
    }

    /// True when *any* connection WinINET knows about is still proxied.
    pub fn effective_proxy_on() -> bool {
        let mut any = false;
        for connection in active_connections() {
            if let Some(flags) = query_flags(connection.as_deref()) {
                if flags & PROXY_TYPE_PROXY != 0 {
                    any = true;
                }
            }
        }
        let snap = registry_snapshot();
        any || (snap.enable == 1 && !snap.server.is_empty())
    }

    pub fn apply(enable: u32, server: &str, override_list: &str) -> Result<(), String> {
        let hkcu = RegKey::predef(HKEY_CURRENT_USER);
        let key = hkcu
            .open_subkey_with_flags(INTERNET_SETTINGS, KEY_SET_VALUE)
            .map_err(|e| e.to_string())?;
        key.set_value("ProxyEnable", &enable).map_err(|e| e.to_string())?;
        key.set_value("ProxyServer", &server).map_err(|e| e.to_string())?;
        key.set_value("ProxyOverride", &override_list).map_err(|e| e.to_string())?;
        drop(key);

        let proxied = enable == 1;
        let mut errors = Vec::new();
        for connection in active_connections() {
            if let Err(e) = set_options(connection.as_deref(), proxied, server) {
                errors.push(format!("{:?}: {e}", connection));
            }
        }
        refresh();
        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors.join("；"))
        }
    }

    /// Broadcast the change without asking WinINET to re-persist its own cache.
    ///
    /// Calling INTERNET_OPTION_SETTINGS_CHANGED makes WinINET write its in-memory
    /// configuration back to the registry; when that cache still holds a proxy it
    /// silently undoes the change we just made, so only REFRESH is used here.
    fn refresh() {
        unsafe {
            let _ = InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0);
        }
    }
}

#[cfg(target_os = "linux")]
mod imp {
    use std::process::Command;

    use crate::state::ProxySnapshot;

    fn gs_get(key: &str) -> String {
        Command::new("gsettings")
            .args(["get", "org.gnome.system.proxy", key])
            .output()
            .ok()
            .map(|o| {
                String::from_utf8_lossy(&o.stdout)
                    .trim()
                    .trim_matches('\'')
                    .to_string()
            })
            .unwrap_or_default()
    }

    fn gs_set(key: &str, val: &str) -> Result<(), String> {
        let out = Command::new("gsettings")
            .args(["set", "org.gnome.system.proxy", key, val])
            .output()
            .map_err(|e| format!("gsettings 不可用：{e}"))?;
        if out.status.success() {
            Ok(())
        } else {
            Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
        }
    }

    pub fn get_system_proxy() -> ProxySnapshot {
        let mode = gs_get("mode");
        if mode == "manual" {
            let host = gs_get("http.host");
            let port = gs_get("http.port");
            ProxySnapshot {
                enable: 1,
                server: format!("{host}:{port}"),
                override_list: String::new(),
            }
        } else {
            ProxySnapshot {
                enable: 0,
                server: String::new(),
                override_list: mode,
            }
        }
    }

    pub fn apply(enable: u32, server: &str, _ov: &str) -> Result<(), String> {
        if enable == 1 {
            let (host, port) = super::split_host_port(server);
            let port = port.to_string();
            gs_set("http.host", &host)?;
            gs_set("http.port", &port)?;
            gs_set("https.host", &host)?;
            gs_set("https.port", &port)?;
            gs_set("socks.host", &host)?;
            gs_set("socks.port", &port)?;
            gs_set("mode", "manual")?;
        } else {
            gs_set("mode", "none")?;
        }
        Ok(())
    }
}

#[cfg(target_os = "macos")]
mod imp {
    use std::process::Command;

    use crate::state::ProxySnapshot;

    pub fn get_system_proxy() -> ProxySnapshot {
        let Ok(out) = Command::new("scutil").arg("--proxy").output() else {
            return ProxySnapshot::default();
        };
        let text = String::from_utf8_lossy(&out.stdout);
        let mut enable = 0u32;
        let mut host = String::new();
        let mut port = String::new();
        for line in text.lines() {
            let Some((k, v)) = line.split_once(':') else { continue };
            let k = k.trim();
            let v = v.trim();
            if k == "HTTPEnable" {
                enable = v.parse().unwrap_or(0);
            } else if k == "HTTPProxy" {
                host = v.to_string();
            } else if k == "HTTPPort" {
                port = v.to_string();
            }
        }
        ProxySnapshot {
            enable,
            server: if host.is_empty() {
                String::new()
            } else {
                format!("{host}:{port}")
            },
            override_list: String::new(),
        }
    }

    fn services() -> Vec<String> {
        let Ok(out) = Command::new("networksetup").arg("-listallnetworkservices").output() else {
            return vec![];
        };
        String::from_utf8_lossy(&out.stdout)
            .lines()
            .skip(1)
            .map(|l| l.trim().trim_start_matches('*').trim().to_string())
            .filter(|l| !l.is_empty())
            .collect()
    }

    pub fn apply(enable: u32, server: &str, _ov: &str) -> Result<(), String> {
        let svcs = services();
        if svcs.is_empty() {
            return Err("找不到網路服務，請在系統設定中手動設定代理".into());
        }
        if enable == 1 {
            let (host, port) = super::split_host_port(server);
            let port = port.to_string();
            let mut any_ok = false;
            for s in &svcs {
                let ok = Command::new("networksetup")
                    .args(["-setwebproxy", s, &host, &port])
                    .status()
                    .map(|x| x.success())
                    .unwrap_or(false);
                let ok2 = Command::new("networksetup")
                    .args(["-setsecurewebproxy", s, &host, &port])
                    .status()
                    .map(|x| x.success())
                    .unwrap_or(false);
                any_ok |= ok || ok2;
            }
            if !any_ok {
                return Err(
                    "設定系統代理失敗（可能需要管理員權限）；請手動把 HTTP/SOCKS 代理指到 127.0.0.1:埠號"
                        .into(),
                );
            }
        } else {
            for s in &svcs {
                let _ = Command::new("networksetup")
                    .args(["-setwebproxystate", s, "off"])
                    .status();
                let _ = Command::new("networksetup")
                    .args(["-setsecurewebproxystate", s, "off"])
                    .status();
            }
        }
        Ok(())
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
mod imp {
    use crate::state::ProxySnapshot;

    pub fn get_system_proxy() -> ProxySnapshot {
        ProxySnapshot::default()
    }

    pub fn apply(_enable: u32, _server: &str, _ov: &str) -> Result<(), String> {
        Err("此平台不支援自動系統代理".into())
    }
}

pub use imp::{apply, get_system_proxy};

#[derive(Debug, Clone, Default, Serialize)]
pub struct ProxyRecovery {
    pub attempted: bool,
    pub restored: bool,
    pub cleared_stale: bool,
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum RecoveryAction {
    None,
    Restore(ProxySnapshot),
    ClearStale,
}

fn recovery_action(
    original: Option<&ProxySnapshot>,
    current: &ProxySnapshot,
    expected_server: &str,
) -> RecoveryAction {
    let Some(original) = original else {
        return RecoveryAction::None;
    };
    if current.enable == 1 && current.server.trim() == expected_server {
        RecoveryAction::Restore(original.clone())
    } else {
        RecoveryAction::ClearStale
    }
}

pub fn recover_stale_proxy(store: &mut Store) -> ProxyRecovery {
    let original = store.data.original_proxy.clone();
    if original.is_none() {
        return ProxyRecovery::default();
    }
    let current = get_system_proxy();
    let expected = format!("127.0.0.1:{}", store.data.mixed_port);
    match recovery_action(original.as_ref(), &current, &expected) {
        RecoveryAction::None => ProxyRecovery::default(),
        RecoveryAction::Restore(original) => match apply(
            original.enable,
            &original.server,
            &original.override_list,
        ) {
            Ok(()) => {
                store.data.original_proxy = None;
                let mut recovery = ProxyRecovery {
                    attempted: true,
                    restored: true,
                    ..ProxyRecovery::default()
                };
                if let Err(e) = store.save() {
                    recovery.error = Some(format!("代理已恢復，但設定檔儲存失敗：{e}"));
                }
                recovery
            }
            Err(e) => ProxyRecovery {
                attempted: true,
                error: Some(format!("偵測到上次未清理的系統代理，但恢復失敗：{e}")),
                ..ProxyRecovery::default()
            },
        },
        RecoveryAction::ClearStale => {
            store.data.original_proxy = None;
            let mut recovery = ProxyRecovery {
                attempted: true,
                cleared_stale: true,
                ..ProxyRecovery::default()
            };
            if let Err(e) = store.save() {
                recovery.error = Some(format!("已忽略過期代理快照，但設定檔儲存失敗：{e}"));
            }
            recovery
        }
    }
}

pub fn is_on(_store: &Store) -> bool {
    let cur = get_system_proxy();
    cur.enable == 1 && cur.server.contains("127.0.0.1:")
}

/// True when any system proxy is enabled, whoever configured it.
///
/// On Windows this asks WinINET about every connection (LAN and each active
/// RAS/VPN dial-up) instead of trusting `ProxyEnable` alone: Windows can keep a
/// per-connection proxy that the registry values do not show.
pub fn any_proxy_on() -> bool {
    #[cfg(windows)]
    {
        imp::effective_proxy_on()
    }
    #[cfg(not(windows))]
    {
        get_system_proxy().enable == 1
    }
}

/// Turn the system proxy off and verify that Windows really applied it.
///
/// Windows keeps a WinINET copy of the proxy settings in memory; when that copy
/// still says "proxy on", it can be written back to the registry seconds later
/// and only a new logon clears it. Callers must surface that to the user instead
/// of pretending the toggle worked.
pub fn disable_verified(store: &mut Store, core_up: bool) -> Result<bool, String> {
    set_system_proxy(store, false, core_up)?;
    for _ in 0..5 {
        if !any_proxy_on() {
            return Ok(true);
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    Ok(false)
}

pub fn set_system_proxy(store: &mut Store, enabled: bool, core_up: bool) -> Result<bool, String> {
    if enabled {
        if !core_up {
            return Err("核心未啟動，請先啟動核心".into());
        }
        let cur = get_system_proxy();
        let ours = cur.enable == 1 && cur.server.starts_with("127.0.0.1:");
        let captured_now = !ours && store.data.original_proxy.is_none();
        if captured_now {
            store.data.original_proxy = Some(cur);
            store.save()?;
        }
        if let Err(e) = apply(
            1,
            &format!("127.0.0.1:{}", store.data.mixed_port),
            PROXY_OVERRIDE,
        ) {
            if captured_now {
                store.data.original_proxy = None;
                let _ = store.save();
            }
            return Err(e);
        }
        let _ = store.save();
        std::thread::sleep(std::time::Duration::from_millis(1200));
        if !is_on(store) {
            if captured_now {
                store.data.original_proxy = None;
                let _ = store.save();
            }
            return Err(
                "系統代理被其他軟體改回（常見於安全軟體／網路加速器的代理守護）。請關閉該功能後再試。"
                    .into(),
            );
        }
    } else {
        let original = store.data.original_proxy.clone();
        match original {
            Some(orig) => apply(orig.enable, &orig.server, &orig.override_list)?,
            None => apply(0, "", "")?,
        }
        store.data.original_proxy = None;
        store.save()?;
    }
    Ok(is_on(store))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot(enable: u32, server: &str) -> ProxySnapshot {
        ProxySnapshot {
            enable,
            server: server.into(),
            override_list: String::new(),
        }
    }

    #[test]
    fn only_recovers_when_current_proxy_matches_kumoroute() {
        let original = snapshot(1, "10.0.0.1:8080");
        assert_eq!(
            recovery_action(
                Some(&original),
                &snapshot(1, "127.0.0.1:7890"),
                "127.0.0.1:7890"
            ),
            RecoveryAction::Restore(original.clone())
        );
        assert_eq!(
            recovery_action(
                Some(&original),
                &snapshot(1, "127.0.0.1:9999"),
                "127.0.0.1:7890"
            ),
            RecoveryAction::ClearStale
        );
        assert_eq!(
            recovery_action(None, &snapshot(1, "127.0.0.1:7890"), "127.0.0.1:7890"),
            RecoveryAction::None
        );
    }

    /// Live-machine check: disables the proxy through WinINET and asserts the
    /// effective state really changed. Ignored by default because it touches the
    /// host; run with `cargo test -- --ignored live_disable_proxy`.
    #[test]
    #[ignore]
    fn live_dump_proxy() {
        #[cfg(windows)]
        {
            for connection in imp::active_connections() {
                let flags = imp::query_flags(connection.as_deref());
                println!("conn={:?} flags={:?}", connection, flags);
            }
            println!("registry={:?}", get_system_proxy());
            let _ = apply(0, "", PROXY_OVERRIDE);
            std::thread::sleep(std::time::Duration::from_millis(300));
            println!("--- after apply(0) ---");
            for connection in imp::active_connections() {
                let flags = imp::query_flags(connection.as_deref());
                println!("conn={:?} flags={:?}", connection, flags);
            }
            println!("registry={:?}", get_system_proxy());
            println!("effective={}", imp::effective_proxy_on());
        }
    }

    #[test]
    #[ignore]
    fn live_disable_proxy() {
        apply(0, "", PROXY_OVERRIDE).expect("apply failed");
        std::thread::sleep(std::time::Duration::from_millis(600));
        assert!(!any_proxy_on(), "WinINET still reports a proxy after apply(0)");
        for connection in {
            #[cfg(windows)]
            {
                imp::active_connections()
            }
            #[cfg(not(windows))]
            {
                Vec::new()
            }
        } {
            let _ = connection;
        }
    }

    #[test]
    fn external_proxy_change_is_not_overwritten() {
        let original = snapshot(0, "");
        assert_eq!(
            recovery_action(
                Some(&original),
                &snapshot(1, "192.168.1.10:3128"),
                "127.0.0.1:7890"
            ),
            RecoveryAction::ClearStale
        );
    }
}
