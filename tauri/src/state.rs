use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use regex::Regex;
use serde::{Deserialize, Serialize};

pub const APP_NAME: &str = "KumoRoute";
pub const LEGACY_APP_NAME: &str = "MyClash";
pub const APP_VERSION: &str = "0.7.0";
pub const SUB_UA: &str = concat!("KumoRoute/", env!("CARGO_PKG_VERSION"));
pub const TEST_URL: &str = "https://cp.cloudflare.com/generate_204";

pub const BUILTIN_CONFIG: &str = "mode: rule\nlog-level: info\nproxies: []\nrules:\n  - MATCH,DIRECT\n";

pub fn data_dir() -> PathBuf {
    let d = if let Some(path) = std::env::var_os("KUMOROUTE_DATA_DIR") {
        PathBuf::from(path)
    } else {
        let base = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
        let d = base.join(APP_NAME);
        let legacy = base.join(LEGACY_APP_NAME);
        if !d.exists() && legacy.is_dir() {
            let _ = fs::rename(&legacy, &d);
        }
        d
    };
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

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct RedactionSummary {
    pub urls: usize,
    pub endpoints: usize,
    pub ips: usize,
    pub secrets: usize,
}

#[derive(Debug, Clone)]
pub struct SanitizedDiagnostics {
    pub text: String,
    pub summary: RedactionSummary,
}

fn regex_cell(pattern: &'static str) -> &'static Regex {
    static CACHE: OnceLock<std::sync::Mutex<std::collections::HashMap<&'static str, &'static Regex>>> =
        OnceLock::new();
    let cache = CACHE.get_or_init(|| std::sync::Mutex::new(std::collections::HashMap::new()));
    let mut guard = cache.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(re) = guard.get(pattern) {
        return re;
    }
    let re = Box::leak(Box::new(Regex::new(pattern).expect("valid diagnostics regex")));
    guard.insert(pattern, re);
    re
}

pub fn sanitize_diagnostics_report(text: &str) -> SanitizedDiagnostics {
    let endpoint_re = regex_cell(r"(?m)(-->\s*)[^\s]+");
    let url_re = regex_cell(r#"(?i)https?://[^\s"'<>]+"#);
    let ip_re = regex_cell(r"\b(?:\d{1,3}\.){3}\d{1,3}\b");
    let ipv6_re = regex_cell(r#"(?i)\b(?:(?:[0-9a-f]{1,4}:){1,7}:[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}[0-9a-f]{0,3}[a-f][0-9a-f]{0,3})\b"#);
    let secret_re = regex_cell(
        r#"(?i)\b(token|secret|password|passwd|authorization|api[_-]?key|access[_-]?token)\b(\s*[:=]\s*)([^\s,;"'<>]+)"#,
    );
    let bearer_re = regex_cell(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+");

    let mut summary = RedactionSummary::default();
    summary.endpoints = endpoint_re.find_iter(text).count();
    let text = endpoint_re.replace_all(text, "${1}<redacted-endpoint>");
    summary.urls = url_re.find_iter(&text).count();
    let text = url_re.replace_all(&text, "<redacted-url>");
    summary.ips = ip_re.find_iter(&text).count() + ipv6_re.find_iter(&text).count();
    let text = ip_re.replace_all(&text, "<redacted-ip>");
    let text = ipv6_re.replace_all(&text, "<redacted-ip>");
    summary.secrets = bearer_re.find_iter(&text).count();
    let text = bearer_re.replace_all(&text, "Bearer <redacted-secret>");
    summary.secrets += secret_re.find_iter(&text).count();
    let text = secret_re.replace_all(&text, "${1}${2}<redacted-secret>");
    SanitizedDiagnostics {
        text: text.to_string(),
        summary,
    }
}

pub fn sanitize_diagnostics(text: &str) -> String {
    sanitize_diagnostics_report(text).text
}

pub fn write_crash(kind: &str, detail: &str) {
    let dir = data_dir().join("logs");
    let _ = fs::create_dir_all(&dir);
    let path = dir.join("crash.log");
    if fs::metadata(&path).map(|m| m.len() > 1024 * 1024).unwrap_or(false) {
        let backup = dir.join("crash.1.log");
        let _ = fs::remove_file(&backup);
        let _ = fs::rename(&path, backup);
    }
    let safe = sanitize_diagnostics(detail);
    let mut start = safe.len().saturating_sub(200_000);
    while start < safe.len() && !safe.is_char_boundary(start) {
        start += 1;
    }
    let tail = &safe[start..];
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(path) {
        use std::io::Write;
        let _ = writeln!(f, "\n===== {} {kind} =====", now());
        let _ = f.write_all(tail.as_bytes());
        let _ = f.write_all(b"\n");
    }
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

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
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
        let text = serde_json::to_string_pretty(&self.data).map_err(|e| e.to_string())?;
        atomic_write(&self.path, &text)
    }
}

fn atomic_write(path: &Path, text: &str) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "設定檔路徑沒有父目錄".to_string())?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let file_name = path
        .file_name()
        .and_then(|v| v.to_str())
        .unwrap_or("state");
    let tmp = parent.join(format!(
        ".{file_name}.{}.tmp",
        uuid::Uuid::new_v4().simple()
    ));
    let result = (|| {
        let mut file = fs::File::create(&tmp).map_err(|e| e.to_string())?;
        file.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        drop(file);
        fs::rename(&tmp, path).map_err(|e| e.to_string())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    result
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
        Self::load_from(data_dir().join("profiles"), store)
    }

    fn load_from(root: PathBuf, store: &mut Store) -> Self {
        let _ = fs::create_dir_all(&root);
        let index = root.join("index.json");
        let mut entries: Vec<Entry> = fs::read_to_string(&index)
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_default();
        if entries.is_empty() {
            let f = root.join("direct.yaml");
            if !f.exists() {
                let _ = atomic_write(&f, BUILTIN_CONFIG);
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
        if let Err(e) = p.save_index() {
            app_log(&format!("profiles index save failed: {e}"));
        }
        let active = store.data.active_profile.clone();
        if active.is_empty() || p.get(&active).is_none() {
            store.data.active_profile = p.entries[0].id.clone();
            let _ = store.save();
        }
        p
    }

    fn save_index(&self) -> Result<(), String> {
        let text = serde_json::to_string_pretty(&self.entries).map_err(|e| e.to_string())?;
        atomic_write(&self.root.join("index.json"), &text)
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
        const MAX_BYTES: u64 = 10 * 1024 * 1024;
        let resp = ureq::get(url)
            .set("User-Agent", SUB_UA)
            .timeout(std::time::Duration::from_secs(25))
            .call()
            .map_err(|e| e.to_string())?;
        if resp
            .header("Content-Length")
            .and_then(|v| v.parse::<u64>().ok())
            .is_some_and(|n| n > MAX_BYTES)
        {
            return Err("訂閱檔案超過 10MB，已中止".into());
        }
        let mut raw = Vec::new();
        resp.into_reader()
            .take(MAX_BYTES + 1)
            .read_to_end(&mut raw)
            .map_err(|e| e.to_string())?;
        if raw.len() as u64 > MAX_BYTES {
            return Err("訂閱檔案超過 10MB，已中止".into());
        }
        String::from_utf8(raw).map_err(|_| "訂閱內容不是有效的 UTF-8 文字".to_string())
    }

    fn validate_remote_url(url: &str) -> Result<(), String> {
        let parsed = url::Url::parse(url).map_err(|_| "訂閱連結格式無效".to_string())?;
        if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
            return Err("訂閱連結必須是有效的 http(s):// 網址".into());
        }
        if !parsed.username().is_empty() || parsed.password().is_some() {
            return Err("訂閱連結不可包含帳號或密碼".into());
        }
        Ok(())
    }

    fn register_entry(&mut self, entry: Entry, text: &str) -> Result<Entry, String> {
        atomic_write(&self.path_of(&entry.id), text)?;
        self.entries.push(entry.clone());
        if let Err(e) = self.save_index() {
            self.entries.retain(|item| item.id != entry.id);
            let _ = fs::remove_file(self.path_of(&entry.id));
            return Err(format!("儲存配置索引失敗：{e}"));
        }
        Ok(entry)
    }

    pub fn add_remote(&mut self, url: &str, name: &str) -> Result<Entry, String> {
        let url = url.trim();
        Self::validate_remote_url(url)?;
        let text = Self::fetch(url)?;
        Self::validate(&text)?;
        let id = uuid::Uuid::new_v4().simple().to_string()[..8].to_string();
        let name = if name.trim().is_empty() {
            url::Url::parse(url)
                .ok()
                .and_then(|parsed| parsed.host_str().map(str::to_string))
                .unwrap_or_else(|| format!("訂閱 {}", self.entries.len() + 1))
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
        self.register_entry(entry, &text)
    }

    pub fn add_local(&mut self, src: &str) -> Result<Entry, String> {
        let p = PathBuf::from(src);
        let text = fs::read_to_string(&p).map_err(|e| e.to_string())?;
        Self::validate(&text)?;
        let id = uuid::Uuid::new_v4().simple().to_string()[..8].to_string();
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
        self.register_entry(entry, &text)
    }

    fn backup_path_of(&self, id: &str) -> PathBuf {
        self.root.join(format!("{id}.yaml.bak"))
    }

    fn apply_remote_text(&mut self, id: &str, text: &str) -> Result<(), String> {
        Self::validate(text)?;
        let entry = self.get(id).cloned().ok_or("找不到該訂閱")?;
        if entry.kind != "remote" || entry.url.is_empty() {
            return Err("只有遠端訂閱可以更新".into());
        }
        let path = self.path_of(id);
        let backup = self.backup_path_of(id);
        fs::copy(&path, &backup).map_err(|e| format!("建立訂閱備份失敗：{e}"))?;
        if let Err(e) = atomic_write(&path, text) {
            let _ = fs::remove_file(&backup);
            return Err(e);
        }
        let previous = entry.clone();
        if let Some(current) = self.entries.iter_mut().find(|item| item.id == id) {
            current.updated_at = now();
        }
        if let Err(e) = self.save_index() {
            let _ = atomic_write(&path, &fs::read_to_string(&backup).unwrap_or_default());
            if let Some(current) = self.entries.iter_mut().find(|item| item.id == id) {
                *current = previous;
            }
            return Err(format!("儲存配置索引失敗，已自動回滾：{e}"));
        }
        Ok(())
    }

    pub fn update(&mut self, id: &str) -> Result<(), String> {
        let entry = self.get(id).cloned().ok_or("找不到該訂閱")?;
        if entry.kind != "remote" || entry.url.is_empty() {
            return Err("只有遠端訂閱可以更新".into());
        }
        Self::validate_remote_url(&entry.url)?;
        let text = Self::fetch(&entry.url)?;
        self.apply_remote_text(id, &text)
    }

    pub fn rollback_to(&mut self, id: &str, previous: &Entry) -> Result<(), String> {
        let backup = self.backup_path_of(id);
        let text = fs::read_to_string(&backup).map_err(|e| format!("找不到可回滾的備份：{e}"))?;
        Self::validate(&text)?;
        atomic_write(&self.path_of(id), &text)?;
        if let Some(current) = self.entries.iter_mut().find(|item| item.id == id) {
            *current = previous.clone();
        }
        self.save_index()
            .map_err(|e| format!("恢復配置索引失敗：{e}"))
    }

    pub fn delete(&mut self, id: &str, store: &mut Store) -> Result<(), String> {
        let entry = self.get(id).cloned().ok_or("找不到該配置")?;
        if entry.kind == "builtin" {
            return Err("內建配置不能刪除".into());
        }
        self.entries.retain(|e| e.id != id);
        self.save_index()?;
        let _ = fs::remove_file(self.path_of(id));
        let _ = fs::remove_file(self.backup_path_of(id));
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
        atomic_write(&out, &yaml)?;
        Ok(out)
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    struct TempDir(PathBuf);

    impl TempDir {
        fn new(name: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "kumoroute-{name}-{}",
                uuid::Uuid::new_v4().simple()
            ));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn test_store(root: &Path) -> Store {
        Store {
            path: root.join("settings.json"),
            data: Settings::default(),
        }
    }

    #[test]
    fn diagnostics_redact_common_secrets() {
        let report = sanitize_diagnostics_report(
            "URL https://user.example/api?token=topsecret\n\
             --> 127.0.0.1:9090\n\
             public 203.0.113.7 ipv6 2001:db8::1\n\
             Authorization: Bearer abc.def token=plain-secret",
        );
        assert!(!report.text.contains("https://"));
        assert!(!report.text.contains("127.0.0.1:9090"));
        assert!(!report.text.contains("203.0.113.7"));
        assert!(!report.text.contains("2001:db8::1"));
        assert!(!report.text.contains("topsecret"));
        assert!(!report.text.contains("plain-secret"));
        assert!(!report.text.contains("abc.def"));
        assert!(report.summary.urls >= 1);
        assert!(report.summary.endpoints >= 1);
        assert!(report.summary.ips >= 2);
        assert!(report.summary.secrets >= 2);
    }

    #[test]
    fn remote_url_validation_rejects_unsafe_forms() {
        assert!(Profiles::validate_remote_url("https://example.com/sub").is_ok());
        assert!(Profiles::validate_remote_url("http://127.0.0.1:8080/sub").is_ok());
        assert!(Profiles::validate_remote_url("ftp://example.com/sub").is_err());
        assert!(Profiles::validate_remote_url("https://user:pass@example.com/sub").is_err());
        assert!(Profiles::validate_remote_url("not a url").is_err());
    }

    #[test]
    fn profile_update_and_rollback_are_transactional() {
        let temp = TempDir::new("profile-rollback");
        let mut store = test_store(&temp.0);
        let mut profiles = Profiles::load_from(temp.0.join("profiles"), &mut store);
        let source = temp.0.join("source.yaml");
        fs::write(
            &source,
            "mode: rule\nproxies: []\nrules:\n  - MATCH,DIRECT\n",
        )
        .unwrap();
        let added = profiles.add_local(source.to_str().unwrap()).unwrap();
        {
            let entry = profiles
                .entries
                .iter_mut()
                .find(|entry| entry.id == added.id)
                .unwrap();
            entry.kind = "remote".into();
            entry.url = "https://example.com/sub".into();
        }
        let previous = profiles.get(&added.id).cloned().unwrap();
        let original = fs::read_to_string(profiles.path_of(&added.id)).unwrap();
        profiles
            .apply_remote_text(&added.id, "mode: global\nproxies: []\n")
            .unwrap();
        assert!(fs::read_to_string(profiles.path_of(&added.id))
            .unwrap()
            .contains("mode: global"));
        profiles.rollback_to(&added.id, &previous).unwrap();
        assert_eq!(fs::read_to_string(profiles.path_of(&added.id)).unwrap(), original);
        assert_eq!(profiles.get(&added.id).unwrap().updated_at, previous.updated_at);
    }

    #[test]
    fn invalid_profile_update_keeps_previous_file() {
        let temp = TempDir::new("profile-invalid");
        let mut store = test_store(&temp.0);
        let mut profiles = Profiles::load_from(temp.0.join("profiles"), &mut store);
        let source = temp.0.join("source.yaml");
        fs::write(&source, "mode: rule\nproxies: []\n").unwrap();
        let added = profiles.add_local(source.to_str().unwrap()).unwrap();
        {
            let entry = profiles
                .entries
                .iter_mut()
                .find(|entry| entry.id == added.id)
                .unwrap();
            entry.kind = "remote".into();
            entry.url = "https://example.com/sub".into();
        }
        let path = profiles.path_of(&added.id);
        let before = fs::read_to_string(&path).unwrap();
        assert!(profiles.apply_remote_text(&added.id, "mode: [broken").is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), before);
    }
}
