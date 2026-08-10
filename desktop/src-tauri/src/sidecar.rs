//! Sidecar lifecycle helpers. Pure READY/health parsers always available;
//! process spawn requires the `gui` feature (ureq/uuid).

use regex::Regex;
use serde::Deserialize;
use thiserror::Error;

pub const READY_DEADLINE_SECS: u64 = 60;
pub const SHUTDOWN_WAIT_SECS: u64 = 5;
pub const HEALTH_POLL_MS: u64 = 100;
pub const HEALTH_REQ_TIMEOUT_MS: u64 = 500;

#[derive(Debug, Error)]
pub enum SidecarError {
    #[error("không tìm thấy binary sidecar: {0}")]
    BinaryMissing(String),
    #[error("spawn sidecar thất bại: {0}")]
    Spawn(String),
    #[error("sidecar thoát trước READY (code={0:?})")]
    ExitedBeforeReady(Option<i32>),
    #[error("hết thời gian chờ READY ({READY_DEADLINE_SECS}s)")]
    ReadyTimeout,
    #[error("READY không hợp lệ: {0}")]
    ReadyInvalid(String),
    #[error("healthz thất bại: {0}")]
    Health(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
}

/// Pure READY line parser (regex exact contract).
pub fn parse_ready_line(line: &str) -> Option<u16> {
    let re = Regex::new(r"^VITRANSCRIPT_READY http://127\.0\.0\.1:(\d+)$").unwrap();
    let caps = re.captures(line.trim_end_matches(['\r', '\n']))?;
    caps.get(1)?.as_str().parse().ok()
}

/// Feed arbitrary stdout chunks; returns port when a full READY line is seen.
pub struct ReadyParser {
    buf: String,
    seen: bool,
}

impl ReadyParser {
    pub fn new() -> Self {
        Self {
            buf: String::new(),
            seen: false,
        }
    }

    pub fn feed(&mut self, chunk: &str) -> Result<Option<u16>, SidecarError> {
        self.buf.push_str(chunk);
        while let Some(pos) = self.buf.find('\n') {
            let mut line = self.buf[..pos].to_string();
            self.buf.drain(..=pos);
            if line.ends_with('\r') {
                line.pop();
            }
            if line.is_empty() {
                continue;
            }
            if let Some(port) = parse_ready_line(&line) {
                if self.seen {
                    return Err(SidecarError::ReadyInvalid("duplicate READY".into()));
                }
                self.seen = true;
                return Ok(Some(port));
            }
        }
        Ok(None)
    }

    pub fn seen(&self) -> bool {
        self.seen
    }
}

impl Default for ReadyParser {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Deserialize)]
struct HealthBody {
    status: String,
    port: u16,
}

pub fn validate_health_json(body: &str, expected_port: u16) -> Result<(), SidecarError> {
    let v: HealthBody =
        serde_json::from_str(body).map_err(|e| SidecarError::Health(format!("json: {e}")))?;
    if v.status != "ok" {
        return Err(SidecarError::Health(format!("status={}", v.status)));
    }
    if v.port != expected_port {
        return Err(SidecarError::Health(format!(
            "port mismatch: got {} expected {}",
            v.port, expected_port
        )));
    }
    Ok(())
}

pub fn host_target_triple() -> String {
    env!("TARGET_TRIPLE").to_string()
}

pub fn sidecar_binary_name_for_triple(triple: &str) -> String {
    if triple.contains("windows") {
        format!("vitranscript-sidecar-{triple}.exe")
    } else {
        format!("vitranscript-sidecar-{triple}")
    }
}

#[cfg(feature = "gui")]
mod runtime {
    use super::*;
    use parking_lot::Mutex;
    use std::io::{BufReader, Read};
    use std::path::{Path, PathBuf};
    use std::process::{Child, Command, Stdio};
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::thread;
    use std::time::{Duration, Instant};

    pub fn poll_healthz(port: u16, overall_deadline: Instant) -> Result<(), SidecarError> {
        let url = format!("http://127.0.0.1:{port}/healthz");
        loop {
            if Instant::now() >= overall_deadline {
                return Err(SidecarError::Health("timeout waiting /healthz".into()));
            }
            let agent = ureq::AgentBuilder::new()
                .timeout_connect(Duration::from_millis(HEALTH_REQ_TIMEOUT_MS))
                .timeout_read(Duration::from_millis(HEALTH_REQ_TIMEOUT_MS))
                .build();
            if let Ok(resp) = agent.get(&url).call() {
                if let Ok(text) = resp.into_string() {
                    if validate_health_json(&text, port).is_ok() {
                        return Ok(());
                    }
                }
            }
            thread::sleep(Duration::from_millis(HEALTH_POLL_MS));
        }
    }

    pub fn resolve_sidecar_path(current_exe: &Path) -> Result<PathBuf, SidecarError> {
        let dir = current_exe
            .parent()
            .ok_or_else(|| SidecarError::BinaryMissing("no parent".into()))?;
        let name = if cfg!(windows) {
            "vitranscript-sidecar.exe"
        } else {
            "vitranscript-sidecar"
        };
        let candidate = dir.join(name);
        if candidate.is_file() {
            return Ok(candidate);
        }
        let triple = host_target_triple();
        let staged = dir.join("../binaries").join(sidecar_binary_name_for_triple(&triple));
        if staged.is_file() {
            return Ok(staged.canonicalize().unwrap_or(staged));
        }
        Err(SidecarError::BinaryMissing(candidate.display().to_string()))
    }

    pub struct SidecarState {
        pub child: Child,
        pub token: String,
        pub port: u16,
        pub ready_url: String,
        pub log_path: PathBuf,
        pub shutting_down: Arc<AtomicBool>,
        #[cfg(unix)]
        pub pgid: i32,
    }

    impl SidecarState {
        pub fn request_shutdown_http(&self) -> Result<(), String> {
            if self
                .shutting_down
                .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                .is_err()
            {
                return Ok(());
            }
            let url = format!("http://127.0.0.1:{}/api/shutdown", self.port);
            let agent = ureq::AgentBuilder::new()
                .timeout_connect(Duration::from_secs(2))
                .timeout_read(Duration::from_secs(3))
                .build();
            match agent
                .post(&url)
                .set("X-ViTranscript-Token", &self.token)
                .call()
            {
                Ok(resp) if resp.status() == 202 => Ok(()),
                Ok(resp) => Err(format!("shutdown status {}", resp.status())),
                Err(e) => Err(format!("shutdown request: {e}")),
            }
        }

        pub fn wait_exit_or_kill(&mut self, wait: Duration) {
            let start = Instant::now();
            while start.elapsed() < wait {
                match self.child.try_wait() {
                    Ok(Some(_)) => return,
                    Ok(None) => thread::sleep(Duration::from_millis(100)),
                    Err(_) => break,
                }
            }
            self.force_kill_tree();
            let _ = self.child.wait();
        }

        pub fn force_kill_tree(&mut self) {
            #[cfg(unix)]
            {
                let pgid = self.pgid;
                unsafe {
                    libc_kill_pg(pgid, 15);
                }
                thread::sleep(Duration::from_secs(2));
                match self.child.try_wait() {
                    Ok(Some(_)) => return,
                    _ => unsafe {
                        libc_kill_pg(pgid, 9);
                    },
                }
            }
            #[cfg(not(unix))]
            {
                let _ = self.child.kill();
            }
        }
    }

    #[cfg(unix)]
    fn libc_kill_pg(pgid: i32, sig: i32) {
        extern "C" {
            fn kill(pid: i32, sig: i32) -> i32;
        }
        unsafe {
            kill(-pgid, sig);
        }
    }

    pub fn generate_token() -> String {
        format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        )
    }

    pub fn spawn_sidecar(
        binary: &Path,
        token: &str,
        log_path: &Path,
    ) -> Result<(Child, Option<i32>), SidecarError> {
        if let Some(parent) = log_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let log_file = std::fs::File::create(log_path)?;
        let log_err = log_file.try_clone()?;

        let mut cmd = Command::new(binary);
        cmd.arg("--port")
            .arg("0")
            .arg("--no-browser")
            .env("VITRANSCRIPT_INSTANCE_TOKEN", token)
            .env("VITRANSCRIPT_DESKTOP", "1")
            .env("PYTHONUNBUFFERED", "1")
            .stdout(Stdio::piped())
            .stderr(Stdio::from(log_err));

        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            unsafe {
                cmd.pre_exec(|| {
                    extern "C" {
                        fn setpgid(pid: i32, pgid: i32) -> i32;
                    }
                    setpgid(0, 0);
                    Ok(())
                });
            }
        }

        let child = cmd.spawn().map_err(|e| SidecarError::Spawn(e.to_string()))?;
        #[cfg(unix)]
        let pgid = Some(child.id() as i32);
        #[cfg(not(unix))]
        let pgid = None;
        let _ = log_file;
        Ok((child, pgid))
    }

    pub fn wait_for_ready(
        child: &mut Child,
        log_path: &Path,
        deadline: Instant,
    ) -> Result<u16, SidecarError> {
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| SidecarError::Spawn("no stdout".into()))?;
        let mut reader = BufReader::new(stdout);
        let mut parser = ReadyParser::new();
        let mut chunk = [0u8; 512];
        let mut log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(log_path)?;

        loop {
            if Instant::now() >= deadline {
                return Err(SidecarError::ReadyTimeout);
            }
            match child.try_wait()? {
                Some(status) if !parser.seen() => {
                    return Err(SidecarError::ExitedBeforeReady(status.code()));
                }
                _ => {}
            }
            match reader.read(&mut chunk) {
                Ok(0) => match child.try_wait()? {
                    Some(status) => return Err(SidecarError::ExitedBeforeReady(status.code())),
                    None => thread::sleep(Duration::from_millis(50)),
                },
                Ok(n) => {
                    let s = String::from_utf8_lossy(&chunk[..n]);
                    let _ = std::io::Write::write_all(&mut log, s.as_bytes());
                    if let Some(port) = parser.feed(&s)? {
                        println!("VITRANSCRIPT_READY http://127.0.0.1:{port}");
                        let _ = std::io::Write::flush(&mut std::io::stdout());
                        return Ok(port);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e.into()),
            }
        }
    }

    pub fn start_and_ready(binary: &Path, data_log_dir: &Path) -> Result<SidecarState, SidecarError> {
        let token = generate_token();
        let log_path = data_log_dir.join("sidecar.log");
        let deadline = Instant::now() + Duration::from_secs(READY_DEADLINE_SECS);
        let (mut child, pgid) = spawn_sidecar(binary, &token, &log_path)?;
        let port = match wait_for_ready(&mut child, &log_path, deadline) {
            Ok(p) => p,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
        };
        if let Err(e) = poll_healthz(port, deadline) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
        Ok(SidecarState {
            child,
            token,
            port,
            ready_url: format!("http://127.0.0.1:{port}"),
            log_path,
            shutting_down: Arc::new(AtomicBool::new(false)),
            #[cfg(unix)]
            pgid: pgid.unwrap_or(0),
        })
    }

    // silence unused Mutex import if not used
    #[allow(dead_code)]
    type _Lock = Mutex<()>;
}

#[cfg(feature = "gui")]
pub use runtime::*;

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    #[test]
    fn ready_parser_exact_line() {
        assert_eq!(
            parse_ready_line("VITRANSCRIPT_READY http://127.0.0.1:8765"),
            Some(8765)
        );
        assert!(parse_ready_line("VITRANSCRIPT_READY http://127.0.0.1:8765 ").is_none());
        assert!(parse_ready_line("VITRANSCRIPT_READY http://0.0.0.0:8765").is_none());
        assert!(parse_ready_line("ready http://127.0.0.1:8765").is_none());
    }

    #[test]
    fn ready_parser_chunked_and_crlf() {
        let mut p = ReadyParser::new();
        assert!(p
            .feed("VITRANSCRIPT_READY http://127.0.0.1:")
            .unwrap()
            .is_none());
        assert_eq!(p.feed("8799\r\n").unwrap(), Some(8799));
    }

    #[test]
    fn ready_parser_duplicate_errors() {
        let mut p = ReadyParser::new();
        assert_eq!(
            p.feed("VITRANSCRIPT_READY http://127.0.0.1:8756\n")
                .unwrap(),
            Some(8756)
        );
        assert!(p
            .feed("VITRANSCRIPT_READY http://127.0.0.1:8757\n")
            .unwrap_err()
            .to_string()
            .contains("duplicate"));
    }

    #[test]
    fn health_validator() {
        assert!(validate_health_json(r#"{"status":"ok","port":8756}"#, 8756).is_ok());
        assert!(validate_health_json(r#"{"status":"ok","port":1}"#, 8756).is_err());
        assert!(validate_health_json(r#"{"status":"bad","port":8756}"#, 8756).is_err());
    }

    #[test]
    fn shutdown_flag_idempotent() {
        let flag = Arc::new(AtomicBool::new(false));
        assert!(flag
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok());
        assert!(flag
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err());
    }

    #[test]
    fn binary_name_four_triples() {
        assert_eq!(
            sidecar_binary_name_for_triple("x86_64-unknown-linux-gnu"),
            "vitranscript-sidecar-x86_64-unknown-linux-gnu"
        );
        assert_eq!(
            sidecar_binary_name_for_triple("aarch64-apple-darwin"),
            "vitranscript-sidecar-aarch64-apple-darwin"
        );
        assert_eq!(
            sidecar_binary_name_for_triple("x86_64-apple-darwin"),
            "vitranscript-sidecar-x86_64-apple-darwin"
        );
        assert_eq!(
            sidecar_binary_name_for_triple("x86_64-pc-windows-msvc"),
            "vitranscript-sidecar-x86_64-pc-windows-msvc.exe"
        );
    }
}
