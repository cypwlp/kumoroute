use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use serde_json::{json, Value};

use crate::state::{core_binary, data_dir};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

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

pub struct Core {
    pub proc: Option<Child>,
}

impl Core {
    pub fn new() -> Self {
        Self { proc: None }
    }

    pub fn start(&mut self, port: u16, runtime: std::path::PathBuf) -> Result<(), String> {
        if is_up(port) {
            return Ok(());
        }
        let bin = core_binary().ok_or("找不到 mihomo 核心（core/mihomo.exe）")?;
        let dd = data_dir();
        let log_path = dd.join("logs").join("core.log");
        let log = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|e| e.to_string())?;
        let log2 = log.try_clone().map_err(|e| e.to_string())?;
        let mut cmd = Command::new(&bin);
        cmd.arg("-d")
            .arg(&dd)
            .arg("-f")
            .arg(&runtime)
            .current_dir(&dd)
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(log2))
            .stdin(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let child = cmd.spawn().map_err(|e| e.to_string())?;
        self.proc = Some(child);
        for _ in 0..48 {
            std::thread::sleep(Duration::from_millis(250));
            if is_up(port) {
                return Ok(());
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
        if let Some(mut child) = self.proc.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    pub fn reload(&mut self, port: u16, runtime: std::path::PathBuf) -> Result<(), String> {
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
