use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE};
use winreg::RegKey;

use crate::state::{ProxySnapshot, Store};

const INTERNET_SETTINGS: &str = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings";

pub const PROXY_OVERRIDE: &str = "<local>;localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*";

pub fn get_system_proxy() -> ProxySnapshot {
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

pub fn apply(enable: u32, server: &str, override_list: &str) -> Result<(), String> {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let key = hkcu
        .open_subkey_with_flags(INTERNET_SETTINGS, KEY_SET_VALUE)
        .map_err(|e| e.to_string())?;
    key.set_value("ProxyEnable", &enable).map_err(|e| e.to_string())?;
    key.set_value("ProxyServer", &server).map_err(|e| e.to_string())?;
    key.set_value("ProxyOverride", &override_list).map_err(|e| e.to_string())?;
    refresh();
    Ok(())
}

fn refresh() {
    use windows::Win32::Networking::WinInet::{
        InternetSetOptionW, INTERNET_OPTION_REFRESH, INTERNET_OPTION_SETTINGS_CHANGED,
    };
    unsafe {
        let _ = InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0);
        let _ = InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0);
    }
}

pub fn is_on(_store: &Store) -> bool {
    let cur = get_system_proxy();
    cur.enable == 1 && cur.server.contains("127.0.0.1:")
}

pub fn set_system_proxy(store: &mut Store, enabled: bool, core_up: bool) -> Result<bool, String> {
    if enabled {
        if !core_up {
            return Err("核心未啟動，請先啟動核心".into());
        }
        let cur = get_system_proxy();
        let ours = cur.enable == 1 && cur.server.starts_with("127.0.0.1:");
        if !ours && store.data.original_proxy.is_none() {
            store.data.original_proxy = Some(cur);
        }
        apply(1, &format!("127.0.0.1:{}", store.data.mixed_port), PROXY_OVERRIDE)?;
        let _ = store.save();
        std::thread::sleep(std::time::Duration::from_millis(1200));
        if !is_on(store) {
            store.data.original_proxy = None;
            let _ = store.save();
            return Err(
                "系統代理被其他軟體改回（常見於安全軟體／網路加速器的代理守護）。請關閉該功能後再試。"
                    .into(),
            );
        }
    } else {
        match store.data.original_proxy.take() {
            Some(orig) => apply(orig.enable, &orig.server, &orig.override_list)?,
            None => apply(0, "", "")?,
        }
        let _ = store.save();
    }
    Ok(is_on(store))
}
