use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex as StdMutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::state::{app_log, core_binary, data_dir, ensure_geo_files};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const MAX_LOG_BYTES: u64 = 2 * 1024 * 1024;

pub fn base_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

pub fn api(method: &str, port: u16, path: &str, body: Option<Value>, timeout: u64) -> Result<Value, String> {
    let url = format!("{}{}", base_url(port), path);
    let req = match method {
        "PUT" => ureq::put(&url),
        "PATCH" => ureq::patch(&url),
        "POST" => ureq::post(&url),
        "DELETE" => ureq::delete(&url),
        _ => ureq::get(&url),
    }
    .timeout(Duration::from_secs(timeout));
    let resp = match body {
        Some(b) => req.send_json(b),
        None => req.call(),
    }
    .map_err(|e| e.to_string())?;
    let text = resp.into_string().map_err(|e| e.to_string())?;
    if text.trim().is_empty() {
        return Ok(Value::Null);
    }
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

pub fn version(port: u16) -> Option<String> {
    api("GET", port, "/version", None, 2)
        .ok()?
        .get("version")?
        .as_str()
        .map(|s| s.to_string())
}

pub fn is_up(port: u16) -> bool {
    version(port).is_some()
}

#[derive(Clone)]
struct SpawnArgs {
    bin: PathBuf,
    dd: PathBuf,
    runtime: PathBuf,
}

fn spawn_child(args: &SpawnArgs) -> Result<Child, String> {
    let log_path = args.dd.join("logs").join("core.log");
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| e.to_string())?;
    let log2 = log.try_clone().map_err(|e| e.to_string())?;
    let mut cmd = Command::new(&args.bin);
    cmd.arg("-d")
        .arg(&args.dd)
        .arg("-f")
        .arg(&args.runtime)
        .current_dir(&args.dd)
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log2))
        .stdin(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.spawn().map_err(|e| e.to_string())
}

fn rotate_core_log(dd: &Path) {
    let p = dd.join("logs").join("core.log");
    if let Ok(md) = std::fs::metadata(&p) {
        if md.len() > MAX_LOG_BYTES {
            let bak = dd.join("logs").join("core.1.log");
            let _ = std::fs::remove_file(&bak);
            let _ = std::fs::rename(&p, &bak);
        }
    }
}

/// 守護執行緒：核心異常退出時自動重啟；60 秒內超過 5 次則放棄。
fn watchdog(alive: Arc<AtomicBool>, child: Arc<StdMutex<Option<Child>>>, args: SpawnArgs) {
    let mut storms: Vec<Instant> = Vec::new();
    loop {
        std::thread::sleep(Duration::from_secs(2));
        if !alive.load(Ordering::SeqCst) {
            return;
        }
        let exited = {
            let mut g = match child.lock() {
                Ok(g) => g,
                Err(_) => return,
            };
            match g.as_mut() {
                None => false,
                Some(c) => matches!(c.try_wait(), Ok(Some(_))),
            }
        };
        if !exited {
            continue;
        }
        if !alive.load(Ordering::SeqCst) {
            return;
        }
        let now = Instant::now();
        storms.retain(|t| now.duration_since(*t).as_secs() < 60);
        storms.push(now);
        if storms.len() > 5 {
            app_log("core 重複崩潰超過 5 次/分鐘，停止自動重啟");
            alive.store(false, Ordering::SeqCst);
            return;
        }
        app_log("core 異常退出，1.5 秒後自動重啟");
        std::thread::sleep(Duration::from_millis(1500));
        if !alive.load(Ordering::SeqCst) {
            return;
        }
        match spawn_child(&args) {
            Ok(c) => {
                *child.lock().unwrap() = Some(c);
                app_log("core 已自動重啟");
            }
            Err(e) => {
                app_log(&format!("core 自動重啟失敗：{e}"));
                alive.store(false, Ordering::SeqCst);
                return;
            }
        }
    }
}

pub struct Core {
    child: Arc<StdMutex<Option<Child>>>,
    alive: Arc<AtomicBool>,
    #[allow(dead_code)]
    args: Option<SpawnArgs>,
}

impl Core {
    pub fn new() -> Self {
        Self {
            child: Arc::new(StdMutex::new(None)),
            alive: Arc::new(AtomicBool::new(false)),
            args: None,
        }
    }

    pub fn start(&mut self, port: u16, runtime: PathBuf) -> Result<(), String> {
        if is_up(port) {
            return Ok(());
        }
        self.stop();
        ensure_geo_files();
        let bin = core_binary().ok_or("找不到 mihomo 核心（core/mihomo.exe）")?;
        let dd = data_dir();
        rotate_core_log(&dd);
        let args = SpawnArgs { bin, dd, runtime };
        let child = spawn_child(&args)?;
        *self.child.lock().unwrap() = Some(child);
        self.args = Some(args.clone());
        for _ in 0..48 {
            std::thread::sleep(Duration::from_millis(250));
            if is_up(port) {
                self.alive.store(true, Ordering::SeqCst);
                let alive = self.alive.clone();
                let child = self.child.clone();
                std::thread::spawn(move || watchdog(alive, child, args));
                app_log("core up");
                return Ok(());
            }
            let exited = self
                .child
                .lock()
                .unwrap()
                .as_mut()
                .map(|c| matches!(c.try_wait(), Ok(Some(_))))
                .unwrap_or(false);
            if exited {
                break;
            }
        }
        let tail = log_tail(1200);
        self.stop();
        Err(if tail.is_empty() {
            "核心未能在 12 秒內啟動".into()
        } else {
            tail
        })
    }

    pub fn stop(&mut self) {
        self.alive.store(false, Ordering::SeqCst);
        if let Ok(mut g) = self.child.lock() {
            if let Some(mut c) = g.take() {
                let _ = c.kill();
                let _ = c.wait();
            }
        }
        self.args = None;
    }

    pub fn reload(&mut self, port: u16, runtime: PathBuf) -> Result<(), String> {
        if !is_up(port) {
            return Ok(());
        }
        let res = api(
            "PUT",
            port,
            "/configs",
            Some(json!({"path": runtime.to_string_lossy(), "force": true})),
            10,
        );
        if res.is_err() {
            self.stop();
            return self.start(port, runtime);
        }
        Ok(())
    }
}

pub fn log_tail(max_bytes: u64) -> String {
    let p = data_dir().join("logs").join("core.log");
    let mut f = match File::open(&p) {
        Ok(f) => f,
        Err(_) => return String::new(),
    };
    let size = f.metadata().map(|m| m.len()).unwrap_or(0);
    let _ = f.seek(SeekFrom::Start(size.saturating_sub(max_bytes)));
    let mut buf = Vec::new();
    let _ = f.read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let re = regex::Regex::new(r"\x1b\[[0-9;]*m").unwrap();
    let lines: Vec<String> = text
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| re.replace_all(l, "").to_string())
        .collect();
    lines[lines.len().saturating_sub(25)..].join("\n")
}

pub fn log_lines(max: usize) -> Vec<String> {
    let p = data_dir().join("logs").join("core.log");
    let mut f = match File::open(&p) {
        Ok(f) => f,
        Err(_) => return vec![],
    };
    let size = f.metadata().map(|m| m.len()).unwrap_or(0);
    let _ = f.seek(SeekFrom::Start(size.saturating_sub(65536)));
    let mut buf = Vec::new();
    let _ = f.read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let re = regex::Regex::new(r"\x1b\[[0-9;]*m").unwrap();
    let lines: Vec<String> = text
        .lines()
        .map(|l| re.replace_all(l, "").to_string())
        .collect();
    lines[lines.len().saturating_sub(max)..].to_vec()
}
