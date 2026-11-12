use std::fs;
use std::path::PathBuf;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

pub const APP_NAME: &str = "KumoRoute";
pub const LEGACY_APP_NAME: &str = "MyClash";
pub const APP_VERSION: &str = "0.2.2";
pub const SUB_UA: &str = concat!("KumoRoute/", env!("CARGO_PKG_VERSION"));
pub const TEST_URL: &str = "https://cp.cloudflare.com/generate_204";

pub const BUILTIN_CONFIG: &str = "mode: rule\nlog-level: info\nproxies: []\nrules:\n  - MATCH,DIRECT\n";

pub fn data_dir() -> PathBuf {
    let base = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    let d = base.join(APP_NAME);
    let legacy = base.join(LEGACY_APP_NAME);
    if !d.exists() && legacy.is_dir() {
        let _ = fs::rename(&legacy, &d);
    }
    let _ = fs::create_dir_all(d.join("profiles"));
    let _ = fs::create_dir_all(d.join("logs"));
    d
}

static RESOURCE_DIR: OnceLock<PathBuf> = OnceLock::new();

pub fn set_resource_dir(p: PathBuf) {
    let _ = RESOURCE_DIR.set(p);
}

#[cfg(windows)]
fn core_name() -> &'static str {
    "mihomo.exe"
}

#[cfg(target_os = "linux")]
fn core_name() -> &'static str {
    "mihomo"
}

#[cfg(target_os = "macos")]
fn core_name() -> &'static str {
    if cfg!(target_arch = "aarch64") {
        "mihomo-arm64"
    } else {
        "mihomo-x64"
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn core_name() -> &'static str {
    "mihomo"
}

pub fn core_binary() -> Option<PathBuf> {
    let name = core_name();
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Some(exe_dir) = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|x| x.to_path_buf()))
    {
        dirs.push(exe_dir.join("core"));
    }
    if let Some(rd) = RESOURCE_DIR.get() {
        dirs.push(rd.join("core"));
    }
    if let Some(dev) = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent() {
        dirs.push(dev.join("client").join("core"));
    }
    for d in dirs {
        let p = d.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

pub fn now() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

pub fn app_log(msg: &str) {
    let line = format!("[{}] {msg}\n", chrono::Local::now().format("%Y-%m-%d %H:%M:%S"));
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(data_dir().join("logs").join("app.log"))
    {
        use std::io::Write;
        let _ = f.write_all(line.as_bytes());
    }
}

/// 把 core 目錄內置的 geodata 種子到資料目錄，避免 mihomo 首次啟動去 GitHub 下載。
pub fn ensure_geo_files() {
    let Some(bin) = core_binary() else { return };
    let Some(src) = bin.parent().map(|p| p.to_path_buf()) else { return };
    let dd = data_dir();
    for name in ["geoip.metadb", "geosite.dat"] {
        let dst = dd.join(name);
        if !dst.exists() {
            let f = src.join(name);
            if f.exists() {
                let _ = std::fs::copy(&f, &dst);
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProxySnapshot {
    pub enable: u32,
    pub server: String,
    #[serde(rename = "override", default)]
    pub override_list: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub mixed_port: u16,
    pub controller_port: u16,
    pub mode: String,
    pub active_profile: String,
    pub original_proxy: Option<ProxySnapshot>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            mixed_port: 7890,
            controller_port: 9090,
            mode: "rule".into(),
            active_profile: String::new(),
            original_proxy: None,
        }
    }
}

pub struct Store {
    pub path: PathBuf,
    pub data: Settings,
}

impl Store {
    pub fn load() -> Self {
        let path = data_dir().join("settings.json");
        let mut data = Settings::default();
        if let Ok(text) = fs::read_to_string(&path) {
            if let Ok(v) = serde_json::from_str::<Settings>(&text) {
                data = v;
            }
        }
        Self { path, data }
    }

    pub fn save(&self) -> Result<(), String> {
        let tmp = self.path.with_extension("tmp");
        let text = serde_json::to_string_pretty(&self.data).map_err(|e| e.to_string())?;
        fs::write(&tmp, text).map_err(|e| e.to_string())?;
        fs::rename(&tmp, &self.path).map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    pub id: String,
    pub name: String,
    pub kind: String,
    #[serde(default)]
    pub url: String,
    pub updated_at: String,
}

pub struct Profiles {
    pub root: PathBuf,
    pub entries: Vec<Entry>,
}

impl Profiles {
    pub fn load(store: &mut Store) -> Self {
        let root = data_dir().join("profiles");
        let index = root.join("index.json");
        let mut entries: Vec<Entry> = fs::read_to_string(&index)
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_default();
        if entries.is_empty() {
            let f = root.join("direct.yaml");
            if !f.exists() {
                let _ = fs::write(&f, BUILTIN_CONFIG);
            }
            entries.push(Entry {
                id: "direct".into(),
                name: "內建直連（DIRECT）".into(),
                kind: "builtin".into(),
                url: String::new(),
                updated_at: now(),
            });
        }
        let p = Self { root, entries };
        p.save_index();
        let active = store.data.active_profile.clone();
        if active.is_empty() || p.get(&active).is_none() {
            store.data.active_profile = p.entries[0].id.clone();
            let _ = store.save();
        }
        p
    }

    fn save_index(&self) {
        let tmp = self.root.join("index.tmp");
        if let Ok(t) = serde_json::to_string_pretty(&self.entries) {
            let _ = fs::write(&tmp, t);
            let _ = fs::rename(&tmp, self.root.join("index.json"));
        }
    }

    pub fn get(&self, id: &str) -> Option<&Entry> {
        self.entries.iter().find(|e| e.id == id)
    }

    pub fn active_entry(&self, store: &Store) -> Entry {
        self.get(&store.data.active_profile)
            .cloned()
            .unwrap_or_else(|| self.entries[0].clone())
    }

    pub fn path_of(&self, id: &str) -> PathBuf {
        self.root.join(format!("{id}.yaml"))
    }

    fn validate(text: &str) -> Result<(), String> {
        let v: serde_yaml::Value =
            serde_yaml::from_str(text).map_err(|e| format!("YAML 解析失敗：{e}"))?;
        if !v.is_mapping() {
            return Err(
                "訂閱內容不是 Clash YAML 配置（可能是 Base64 節點清單），請先轉換成 Clash 格式再匯入。"
                    .into(),
            );
        }
        Ok(())
    }

    fn fetch(url: &str) -> Result<String, String> {
        let resp = ureq::get(url)
            .set("User-Agent", SUB_UA)
            .timeout(std::time::Duration::from_secs(25))
            .call()
            .map_err(|e| e.to_string())?;
        let text = resp.into_string().map_err(|e| e.to_string())?;
        if text.len() > 10 * 1024 * 1024 {
            return Err("訂閱檔案超過 10MB，已中止".into());
        }
        Ok(text)
    }

    pub fn add_remote(&mut self, url: &str, name: &str) -> Result<Entry, String> {
        let url = url.trim();
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return Err("訂閱連結必須是 http(s):// 開頭".into());
        }
        let text = Self::fetch(url)?;
        Self::validate(&text)?;
        let id = uuid::Uuid::new_v4().simple().to_string()[..8].to_string();
        fs::write(self.path_of(&id), &text).map_err(|e| e.to_string())?;
        let name = if name.trim().is_empty() {
            url::host(url).unwrap_or_else(|| format!("訂閱 {}", self.entries.len() + 1))
        } else {
            name.trim().to_string()
        };
        let entry = Entry {
            id,
            name,
            kind: "remote".into(),
            url: url.to_string(),
            updated_at: now(),
        };
        self.entries.push(entry.clone());
        self.save_index();
        Ok(entry)
    }

    pub fn add_local(&mut self, src: &str) -> Result<Entry, String> {
        let p = PathBuf::from(src);
        let text = fs::read_to_string(&p).map_err(|e| e.to_string())?;
        Self::validate(&text)?;
        let id = uuid::Uuid::new_v4().simple().to_string()[..8].to_string();
        fs::write(self.path_of(&id), &text).map_err(|e| e.to_string())?;
        let name = p
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "本機配置".into());
        let entry = Entry {
            id,
            name,
            kind: "local".into(),
            url: String::new(),
            updated_at: now(),
        };
        self.entries.push(entry.clone());
        self.save_index();
        Ok(entry)
    }

    pub fn update(&mut self, id: &str) -> Result<(), String> {
        let entry = self.get(id).cloned().ok_or("找不到該訂閱")?;
        if entry.kind != "remote" || entry.url.is_empty() {
            return Err("只有遠端訂閱可以更新".into());
        }
        let text = Self::fetch(&entry.url)?;
        Self::validate(&text)?;
        fs::write(self.path_of(id), &text).map_err(|e| e.to_string())?;
        if let Some(e) = self.entries.iter_mut().find(|e| e.id == id) {
            e.updated_at = now();
        }
        self.save_index();
        Ok(())
    }

    pub fn delete(&mut self, id: &str, store: &mut Store) -> Result<(), String> {
        let entry = self.get(id).cloned().ok_or("找不到該配置")?;
        if entry.kind == "builtin" {
            return Err("內建配置不能刪除".into());
        }
        self.entries.retain(|e| e.id != id);
        self.save_index();
        let _ = fs::remove_file(self.path_of(id));
        if store.data.active_profile == id {
            store.data.active_profile = self.entries[0].id.clone();
            let _ = store.save();
        }
        Ok(())
    }

    pub fn build_runtime(&self, store: &Store) -> Result<PathBuf, String> {
        let entry = self.active_entry(store);
        let text = fs::read_to_string(self.path_of(&entry.id)).map_err(|e| e.to_string())?;
        let mut cfg: serde_yaml::Value = serde_yaml::from_str(&text).unwrap_or(serde_yaml::Value::Null);
        if !cfg.is_mapping() {
            cfg = serde_yaml::Value::Mapping(Default::default());
        }
        let m = cfg.as_mapping_mut().unwrap();
        let set = |m: &mut serde_yaml::Mapping, k: &str, v: serde_yaml::Value| {
            m.insert(serde_yaml::Value::String(k.into()), v);
        };
        set(m, "mixed-port", store.data.mixed_port.into());
        set(m, "allow-lan", false.into());
        set(
            m,
            "external-controller",
            format!("127.0.0.1:{}", store.data.controller_port).into(),
        );
        set(m, "secret", "".into());
        set(m, "mode", store.data.mode.clone().into());
        set(m, "log-level", "info".into());
        if !m.contains_key(serde_yaml::Value::String("unified-delay".into())) {
            set(m, "unified-delay", true.into());
        }
        if !m.contains_key(serde_yaml::Value::String("tcp-concurrent".into())) {
            set(m, "tcp-concurrent", true.into());
        }
        let prof = m
            .entry(serde_yaml::Value::String("profile".into()))
            .or_insert_with(|| serde_yaml::Value::Mapping(Default::default()));
        if let Some(pm) = prof.as_mapping_mut() {
            pm.insert(
                serde_yaml::Value::String("store-selected".into()),
                true.into(),
            );
        }
        let rules = m
            .entry(serde_yaml::Value::String("rules".into()))
            .or_insert_with(|| serde_yaml::Value::Sequence(vec![]));
        if let Some(seq) = rules.as_sequence_mut() {
            let has_match = seq.iter().any(|r| {
                r.as_str()
                    .map(|s| s.trim().to_uppercase().starts_with("MATCH"))
                    .unwrap_or(false)
            });
            if !has_match {
                seq.push("MATCH,DIRECT".into());
            }
        }
        let out = data_dir().join("runtime.yaml");
        let yaml = serde_yaml::to_string(&cfg).map_err(|e| e.to_string())?;
        fs::write(&out, yaml).map_err(|e| e.to_string())?;
        Ok(out)
    }
}

mod url {
    pub fn host(url: &str) -> Option<String> {
        let rest = url.split("://").nth(1)?;
        let host = rest.split(['/', '?', ':']).next()?;
        if host.is_empty() {
            None
        } else {
            Some(host.to_string())
        }
    }
}
