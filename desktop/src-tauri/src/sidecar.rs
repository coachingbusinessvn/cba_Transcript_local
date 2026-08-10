//! Sidecar lifecycle helpers. Pure READY/health parsers always available;
//! process spawn requires the `gui` feature (ureq/uuid).

use regex::Regex;
use serde::Deserialize;
use thiserror::Error;

pub const READY_DEADLINE_SECS: u64 = 60;
pub const SHUTDOWN_WAIT_SECS: u64 = 5;
pub const HEALTH_POLL_MS: u64 = 100;
pub const HEALTH_REQ_TIMEOUT_MS: u64 = 500;
pub const KILL_GRACE_SECS: u64 = 2;

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

/// Exact-origin navigation guard: scheme=http, host=127.0.0.1, port matches sidecar.
/// Rejects userinfo tricks like `http://127.0.0.1:8756@evil.example/`.
pub fn is_allowed_navigation(url: &str, expected_port: u16) -> bool {
    let s = url.trim();
    if s == "about:blank" {
        return true;
    }
    #[cfg(feature = "gui")]
    {
        if let Ok(u) = url::Url::parse(s) {
            return u.scheme() == "http"
                && u.host_str() == Some("127.0.0.1")
                && u.port() == Some(expected_port)
                && u.username().is_empty()
                && u.password().is_none();
        }
        return false;
    }
    #[cfg(not(feature = "gui"))]
    {
        if s.contains('@') {
            return false;
        }
        let hostport = format!("127.0.0.1:{expected_port}");
        let rest = match s.strip_prefix("http://") {
            Some(r) => r,
            None => return false,
        };
        let hp = rest.split(['/', '?', '#']).next().unwrap_or("");
        hp == hostport
    }
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

// ---------------------------------------------------------------------------
// Stdout drain + READY wait (pure std — unit-testable without Tauri/WebKit)
// ---------------------------------------------------------------------------

use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::mpsc::{self, RecvTimeoutError};
use std::thread;
use std::time::{Duration, Instant};

/// Spawn a stdout drain thread that:
/// - always appends raw bytes to `log_path` for the process lifetime (R2-2);
/// - sends at most one READY port (or error) on the channel;
/// - never stops draining just because the startup receiver was dropped.
pub fn spawn_stdout_drain(
    stdout: impl Read + Send + 'static,
    log_path: PathBuf,
) -> (
    mpsc::Receiver<Result<u16, SidecarError>>,
    thread::JoinHandle<()>,
) {
    let (tx, rx) = mpsc::channel::<Result<u16, SidecarError>>();
    let join = thread::spawn(move || {
        let mut reader = stdout;
        let mut buf = [0u8; 512];
        let mut parser = ReadyParser::new();
        let mut log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .ok();
        // Option so we can drop the sender after first READY/error and keep reading.
        let mut tx_opt = Some(tx);
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    if let Some(ref mut f) = log {
                        let _ = f.write_all(&buf[..n]);
                        let _ = f.flush();
                    }
                    let s = String::from_utf8_lossy(&buf[..n]);
                    if let Some(ref tx) = tx_opt {
                        match parser.feed(&s) {
                            Ok(Some(port)) => {
                                let _ = tx.send(Ok(port));
                                // Stop sending startup events; keep draining stdout.
                                tx_opt = None;
                            }
                            Ok(None) => {}
                            Err(e) => {
                                let _ = tx.send(Err(e));
                                tx_opt = None;
                            }
                        }
                    } else {
                        // Still parse for logging duplicate READY (best-effort).
                        let _ = parser.feed(&s);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => {
                    if let Some(tx) = tx_opt.take() {
                        let _ = tx.send(Err(SidecarError::Spawn(format!("stdout read: {e}"))));
                    }
                    break;
                }
            }
        }
    });
    (rx, join)
}

/// Wait for READY from drain channel with deadline + exit polling.
/// Returns (port, join_handle). Caller owns the join handle for process lifetime.
pub fn wait_for_ready_from_drain(
    rx: mpsc::Receiver<Result<u16, SidecarError>>,
    join: thread::JoinHandle<()>,
    mut try_exit: impl FnMut() -> Result<Option<Option<i32>>, SidecarError>,
    deadline: Instant,
) -> Result<(u16, thread::JoinHandle<()>), SidecarError> {
    loop {
        let now = Instant::now();
        if now >= deadline {
            return Err(SidecarError::ReadyTimeout);
        }
        match try_exit()? {
            Some(code) => {
                return Err(SidecarError::ExitedBeforeReady(code));
            }
            None => {}
        }
        let slice = deadline
            .saturating_duration_since(now)
            .min(Duration::from_millis(200));
        match rx.recv_timeout(slice) {
            Ok(Ok(port)) => {
                println!("VITRANSCRIPT_READY http://127.0.0.1:{port}");
                let _ = std::io::stdout().flush();
                return Ok((port, join));
            }
            Ok(Err(e)) => return Err(e),
            Err(RecvTimeoutError::Timeout) => continue,
            Err(RecvTimeoutError::Disconnected) => match try_exit()? {
                Some(code) => return Err(SidecarError::ExitedBeforeReady(code)),
                None if Instant::now() >= deadline => return Err(SidecarError::ReadyTimeout),
                None => {
                    return Err(SidecarError::Spawn("stdout closed before READY".into()));
                }
            },
        }
    }
}

/// Signal a Unix process group (negative pid). Used by runtime + integration tests.
#[cfg(unix)]
pub fn unix_kill_pg(pgid: i32, sig: i32) {
    if pgid <= 0 {
        return;
    }
    extern "C" {
        fn kill(pid: i32, sig: i32) -> i32;
    }
    unsafe {
        let _ = kill(-pgid, sig);
    }
}

#[cfg(feature = "gui")]
mod runtime {
    use super::*;
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
            let remaining = overall_deadline.saturating_duration_since(Instant::now());
            let slice = remaining
                .min(Duration::from_millis(HEALTH_REQ_TIMEOUT_MS))
                .max(Duration::from_millis(50));
            let agent = ureq::AgentBuilder::new()
                .timeout_connect(slice)
                .timeout_read(slice)
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
        let staged = dir
            .join("../binaries")
            .join(sidecar_binary_name_for_triple(&triple));
        if staged.is_file() {
            return Ok(staged.canonicalize().unwrap_or(staged));
        }
        Err(SidecarError::BinaryMissing(candidate.display().to_string()))
    }

    pub struct SidecarState {
        pub token: String,
        pub port: u16,
        pub ready_url: String,
        pub log_path: PathBuf,
        pub shutting_down: Arc<AtomicBool>,
        #[cfg(unix)]
        child: Child,
        #[cfg(unix)]
        pgid: i32,
        #[cfg(windows)]
        win: windows_proc::WinProc,
        /// Keeps the stdout drain thread alive for the process lifetime (R2-2).
        stdout_reader: Option<thread::JoinHandle<()>>,
        cleaned: bool,
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

        /// Wait up to `wait` for graceful exit, then always clean the process tree.
        ///
        /// Important (finding #4): do **not** return early just because the leader
        /// reaped — descendants may still be alive. Always run group/job kill after
        /// the grace window (or immediately after leader exit so orphans die).
        pub fn wait_exit_or_kill(&mut self, wait: Duration) {
            let start = Instant::now();
            while start.elapsed() < wait {
                if self.try_reap() {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
            // Always signal group/job — even if leader already exited.
            self.force_kill_tree();
            let end = Instant::now() + Duration::from_secs(3);
            while Instant::now() < end {
                if self.try_reap() {
                    break;
                }
                thread::sleep(Duration::from_millis(50));
            }
            self.join_stdout_reader();
            self.cleaned = true;
        }

        fn try_reap(&mut self) -> bool {
            #[cfg(unix)]
            {
                matches!(self.child.try_wait(), Ok(Some(_)))
            }
            #[cfg(windows)]
            {
                self.win.try_wait().is_some()
            }
        }

        fn join_stdout_reader(&mut self) {
            if let Some(h) = self.stdout_reader.take() {
                let _ = h.join();
            }
        }

        /// TERM group/job → grace → KILL group/job. Idempotent.
        /// Safe to call when the leader is already reaped (still signals group).
        pub fn force_kill_tree(&mut self) {
            #[cfg(unix)]
            {
                let pgid = self.pgid;
                if pgid > 0 {
                    unix_kill_pg(pgid, 15); // SIGTERM
                    thread::sleep(Duration::from_secs(KILL_GRACE_SECS));
                    // Always signal group again — leader may be reaped while descendants live.
                    unix_kill_pg(pgid, 9); // SIGKILL
                }
                let _ = self.child.kill();
                let _ = self.child.try_wait();
            }
            #[cfg(windows)]
            {
                self.win.terminate_via_job();
            }
            self.cleaned = true;
        }
    }

    impl Drop for SidecarState {
        fn drop(&mut self) {
            // Drop must never skip tree cleanup (#4). force_kill is idempotent;
            // even after leader reap we still signal the group/job.
            if !self.cleaned {
                self.force_kill_tree();
            } else {
                // Re-signal once more without grace sleep to catch late descendants.
                #[cfg(unix)]
                {
                    if self.pgid > 0 {
                        unix_kill_pg(self.pgid, 9);
                    }
                }
                #[cfg(windows)]
                {
                    self.win.terminate_via_job();
                }
            }
            self.join_stdout_reader();
        }
    }

    pub fn generate_token() -> String {
        format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        )
    }

    // -----------------------------------------------------------------------
    // Unix spawn + READY wait
    // -----------------------------------------------------------------------

    #[cfg(unix)]
    fn install_parent_death_watch() {
        // Linux: kernel delivers signal when parent dies (survives exec).
        #[cfg(target_os = "linux")]
        {
            const PR_SET_PDEATHSIG: i32 = 1;
            extern "C" {
                fn prctl(option: i32, arg2: u64, arg3: u64, arg4: u64, arg5: u64) -> i32;
                fn getppid() -> i32;
                fn raise(sig: i32) -> i32;
            }
            unsafe {
                let _ = prctl(PR_SET_PDEATHSIG, 15, 0, 0, 0); // SIGTERM
                // Race: parent already dead between fork and prctl.
                if getppid() == 1 {
                    let _ = raise(15);
                }
            }
        }
        // macOS / other Unix: poll parent pid from a forked watcher (survives exec
        // of the main child). Watcher is in the same process group and kills the
        // group when the original parent (Tauri) disappears.
        #[cfg(not(target_os = "linux"))]
        {
            extern "C" {
                fn fork() -> i32;
                fn getppid() -> i32;
                fn kill(pid: i32, sig: i32) -> i32;
                fn _exit(code: i32) -> !;
                fn usleep(usec: u32) -> i32;
            }
            unsafe {
                let tauri_pid = getppid();
                match fork() {
                    -1 => {}
                    0 => {
                        // Watcher process.
                        loop {
                            if kill(tauri_pid, 0) != 0 {
                                // Kill our process group (sidecar leader + descendants).
                                let _ = kill(0, 15);
                                usleep(2_000_000);
                                let _ = kill(0, 9);
                                _exit(0);
                            }
                            usleep(500_000);
                        }
                    }
                    _ => {} // continue to exec in the main child
                }
            }
        }
    }

    #[cfg(unix)]
    fn spawn_unix(binary: &Path, token: &str, log_path: &Path) -> Result<(Child, i32), SidecarError> {
        use std::os::unix::process::CommandExt;
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
        // New process group; spawn fails if setpgid fails.
        cmd.process_group(0);
        // Parent-death strategy after setpgid (pre_exec runs in child).
        unsafe {
            cmd.pre_exec(|| {
                install_parent_death_watch();
                Ok(())
            });
        }
        let child = cmd.spawn().map_err(|e| SidecarError::Spawn(e.to_string()))?;
        let pgid = child.id() as i32;
        let _ = log_file;
        Ok((child, pgid))
    }

    #[cfg(unix)]
    fn force_kill_unix(child: &mut Child, pgid: i32) {
        if pgid > 0 {
            unix_kill_pg(pgid, 15);
            thread::sleep(Duration::from_millis(300));
            unix_kill_pg(pgid, 9);
        }
        let _ = child.kill();
        let _ = child.wait();
    }

    #[cfg(unix)]
    pub fn start_and_ready(binary: &Path, data_log_dir: &Path) -> Result<SidecarState, SidecarError> {
        let token = generate_token();
        let log_path = data_log_dir.join("sidecar.log");
        let deadline = Instant::now() + Duration::from_secs(READY_DEADLINE_SECS);

        let (mut child, pgid) = spawn_unix(binary, &token, &log_path)?;
        let stdout = match child.stdout.take() {
            Some(s) => s,
            None => {
                force_kill_unix(&mut child, pgid);
                return Err(SidecarError::Spawn("no stdout".into()));
            }
        };

        let (rx, join) = spawn_stdout_drain(stdout, log_path.clone());
        let (port, stdout_reader) = {
            let child_ref = &mut child;
            match wait_for_ready_from_drain(
                rx,
                join,
                || match child_ref.try_wait()? {
                    Some(st) => Ok(Some(st.code())),
                    None => Ok(None),
                },
                deadline,
            ) {
                Ok(v) => v,
                Err(e) => {
                    force_kill_unix(&mut child, pgid);
                    return Err(e);
                }
            }
        };

        if let Err(e) = poll_healthz(port, deadline) {
            force_kill_unix(&mut child, pgid);
            let _ = stdout_reader.join();
            return Err(e);
        }

        Ok(SidecarState {
            token,
            port,
            ready_url: format!("http://127.0.0.1:{port}"),
            log_path,
            shutting_down: Arc::new(AtomicBool::new(false)),
            child,
            pgid,
            stdout_reader: Some(stdout_reader),
            cleaned: false,
        })
    }

    // -----------------------------------------------------------------------
    // Windows: CreateProcessW suspended + Job Object + ResumeThread
    // -----------------------------------------------------------------------

    #[cfg(windows)]
    pub fn start_and_ready(binary: &Path, data_log_dir: &Path) -> Result<SidecarState, SidecarError> {
        let token = generate_token();
        let log_path = data_log_dir.join("sidecar.log");
        let deadline = Instant::now() + Duration::from_secs(READY_DEADLINE_SECS);

        let mut win =
            windows_proc::spawn_with_job(binary, &token, &log_path).map_err(SidecarError::Spawn)?;
        let stdout = match win.take_stdout() {
            Some(s) => s,
            None => {
                win.terminate_via_job();
                return Err(SidecarError::Spawn("no stdout".into()));
            }
        };

        let (rx, join) = spawn_stdout_drain(stdout, log_path.clone());
        let (port, stdout_reader) = {
            let win_ref = &mut win;
            match wait_for_ready_from_drain(
                rx,
                join,
                || Ok(win_ref.try_wait().map(Some)),
                deadline,
            ) {
                Ok(v) => v,
                Err(e) => {
                    win.terminate_via_job();
                    return Err(e);
                }
            }
        };

        if let Err(e) = poll_healthz(port, deadline) {
            win.terminate_via_job();
            let _ = stdout_reader.join();
            return Err(e);
        }

        Ok(SidecarState {
            token,
            port,
            ready_url: format!("http://127.0.0.1:{port}"),
            log_path,
            shutting_down: Arc::new(AtomicBool::new(false)),
            win,
            stdout_reader: Some(stdout_reader),
            cleaned: false,
        })
    }

    #[cfg(windows)]
    mod windows_proc {
        use super::*;
        use std::fs::File;
        use std::os::windows::io::{AsRawHandle, FromRawHandle, RawHandle};
        use std::ptr;
        use windows_sys::Win32::Foundation::{
            CloseHandle, DuplicateHandle, GetLastError, SetHandleInformation, BOOL, HANDLE,
            HANDLE_FLAG_INHERIT, INVALID_HANDLE_VALUE, TRUE, DUPLICATE_SAME_ACCESS,
        };
        use windows_sys::Win32::System::JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
            SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };
        use windows_sys::Win32::System::Pipes::CreatePipe;
        use windows_sys::Win32::System::Threading::{
            CreateProcessW, GetCurrentProcess, GetExitCodeProcess, ResumeThread, TerminateProcess,
            WaitForSingleObject, CREATE_NO_WINDOW, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT,
            PROCESS_INFORMATION, STARTF_USESTDHANDLES, STARTUPINFOW,
        };
        use windows_sys::Win32::Security::SECURITY_ATTRIBUTES;

        const STILL_ACTIVE: u32 = 259;

        pub struct WinProc {
            process: HANDLE,
            job: HANDLE,
            stdout_read: Option<File>,
        }

        // SAFETY: exclusive owner of process/job handles.
        unsafe impl Send for WinProc {}

        impl WinProc {
            pub fn take_stdout(&mut self) -> Option<File> {
                self.stdout_read.take()
            }

            pub fn try_wait(&mut self) -> Option<i32> {
                unsafe {
                    if self.process.is_null() || self.process == INVALID_HANDLE_VALUE {
                        return Some(-1);
                    }
                    let mut code: u32 = 0;
                    if GetExitCodeProcess(self.process, &mut code) == 0 {
                        return None;
                    }
                    if code == STILL_ACTIVE {
                        None
                    } else {
                        Some(code as i32)
                    }
                }
            }

            /// Idempotent tree kill: close Job (KILL_ON_JOB_CLOSE) then terminate process.
            pub fn terminate_via_job(&mut self) {
                unsafe {
                    if !self.job.is_null() && self.job != INVALID_HANDLE_VALUE {
                        let _ = CloseHandle(self.job);
                        self.job = ptr::null_mut();
                    }
                    if !self.process.is_null() && self.process != INVALID_HANDLE_VALUE {
                        let _ = TerminateProcess(self.process, 1);
                        let _ = WaitForSingleObject(self.process, 3000);
                        let _ = CloseHandle(self.process);
                        self.process = ptr::null_mut();
                    }
                }
            }
        }

        impl Drop for WinProc {
            fn drop(&mut self) {
                self.terminate_via_job();
            }
        }

        pub fn spawn_with_job(
            binary: &Path,
            token: &str,
            log_path: &Path,
        ) -> Result<WinProc, String> {
            unsafe { spawn_with_job_inner(binary, token, log_path) }
        }

        unsafe fn spawn_with_job_inner(
            binary: &Path,
            token: &str,
            log_path: &Path,
        ) -> Result<WinProc, String> {
            if let Some(parent) = log_path.parent() {
                std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }

            let mut stdout_read: HANDLE = ptr::null_mut();
            let mut stdout_write: HANDLE = ptr::null_mut();
            let mut sa = SECURITY_ATTRIBUTES {
                nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
                lpSecurityDescriptor: ptr::null_mut(),
                bInheritHandle: TRUE,
            };
            if CreatePipe(&mut stdout_read, &mut stdout_write, &mut sa, 0) == 0 {
                return Err(format!("CreatePipe stdout failed: {}", GetLastError()));
            }
            if SetHandleInformation(stdout_read, HANDLE_FLAG_INHERIT, 0) == 0 {
                let _ = CloseHandle(stdout_read);
                let _ = CloseHandle(stdout_write);
                return Err(format!("SetHandleInformation failed: {}", GetLastError()));
            }

            let log = File::options()
                .create(true)
                .append(true)
                .open(log_path)
                .map_err(|e| e.to_string())?;
            let mut stderr_inherit: HANDLE = ptr::null_mut();
            if DuplicateHandle(
                GetCurrentProcess(),
                log.as_raw_handle() as HANDLE,
                GetCurrentProcess(),
                &mut stderr_inherit,
                0,
                TRUE,
                DUPLICATE_SAME_ACCESS,
            ) == 0
            {
                let _ = CloseHandle(stdout_read);
                let _ = CloseHandle(stdout_write);
                return Err(format!("DuplicateHandle stderr failed: {}", GetLastError()));
            }

            let nul = File::options()
                .read(true)
                .write(true)
                .open("NUL")
                .map_err(|e| e.to_string())?;
            let mut stdin_h: HANDLE = ptr::null_mut();
            if DuplicateHandle(
                GetCurrentProcess(),
                nul.as_raw_handle() as HANDLE,
                GetCurrentProcess(),
                &mut stdin_h,
                0,
                TRUE,
                DUPLICATE_SAME_ACCESS,
            ) == 0
            {
                let _ = CloseHandle(stdout_read);
                let _ = CloseHandle(stdout_write);
                let _ = CloseHandle(stderr_inherit);
                return Err(format!("DuplicateHandle stdin failed: {}", GetLastError()));
            }

            let mut si: STARTUPINFOW = std::mem::zeroed();
            si.cb = std::mem::size_of::<STARTUPINFOW>() as u32;
            si.dwFlags = STARTF_USESTDHANDLES;
            si.hStdInput = stdin_h;
            si.hStdOutput = stdout_write;
            si.hStdError = stderr_inherit;

            let mut pi: PROCESS_INFORMATION = std::mem::zeroed();

            let exe = binary
                .canonicalize()
                .unwrap_or_else(|_| binary.to_path_buf());
            let cmd_line = format!(
                "\"{}\" --port 0 --no-browser",
                exe.to_string_lossy().replace('"', "")
            );
            let mut cmd_wide: Vec<u16> = cmd_line.encode_utf16().chain(std::iter::once(0)).collect();
            let env_block = build_env_block(&[
                ("VITRANSCRIPT_INSTANCE_TOKEN", token),
                ("VITRANSCRIPT_DESKTOP", "1"),
                ("PYTHONUNBUFFERED", "1"),
            ]);

            let flags = CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT;
            let ok = CreateProcessW(
                ptr::null(),
                cmd_wide.as_mut_ptr(),
                ptr::null_mut(),
                ptr::null_mut(),
                TRUE,
                flags,
                env_block.as_ptr() as *const _,
                ptr::null(),
                &si,
                &mut pi,
            );
            let _ = CloseHandle(stdout_write);
            let _ = CloseHandle(stderr_inherit);
            let _ = CloseHandle(stdin_h);
            drop(log);
            drop(nul);

            if ok == 0 {
                let _ = CloseHandle(stdout_read);
                return Err(format!("CreateProcessW failed: {}", GetLastError()));
            }

            let job = CreateJobObjectW(ptr::null(), ptr::null());
            if job.is_null() || job == INVALID_HANDLE_VALUE {
                let _ = TerminateProcess(pi.hProcess, 1);
                let _ = CloseHandle(pi.hThread);
                let _ = CloseHandle(pi.hProcess);
                let _ = CloseHandle(stdout_read);
                return Err(format!("CreateJobObjectW failed: {}", GetLastError()));
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            ) == 0
            {
                let _ = CloseHandle(job);
                let _ = TerminateProcess(pi.hProcess, 1);
                let _ = CloseHandle(pi.hThread);
                let _ = CloseHandle(pi.hProcess);
                let _ = CloseHandle(stdout_read);
                return Err(format!(
                    "SetInformationJobObject failed: {}",
                    GetLastError()
                ));
            }
            if AssignProcessToJobObject(job, pi.hProcess) == 0 {
                let _ = CloseHandle(job);
                let _ = TerminateProcess(pi.hProcess, 1);
                let _ = CloseHandle(pi.hThread);
                let _ = CloseHandle(pi.hProcess);
                let _ = CloseHandle(stdout_read);
                return Err(format!(
                    "AssignProcessToJobObject failed: {}",
                    GetLastError()
                ));
            }

            if ResumeThread(pi.hThread) == u32::MAX {
                let err = GetLastError();
                let _ = CloseHandle(job);
                let _ = TerminateProcess(pi.hProcess, 1);
                let _ = CloseHandle(pi.hThread);
                let _ = CloseHandle(pi.hProcess);
                let _ = CloseHandle(stdout_read);
                return Err(format!("ResumeThread failed: {err}"));
            }
            let _ = CloseHandle(pi.hThread);

            let stdout_file = File::from_raw_handle(stdout_read as RawHandle);

            Ok(WinProc {
                process: pi.hProcess,
                job,
                stdout_read: Some(stdout_file),
            })
        }

        fn build_env_block(overrides: &[(&str, &str)]) -> Vec<u16> {
            use std::collections::BTreeMap;
            let mut map: BTreeMap<String, String> = std::env::vars().collect();
            for (k, v) in overrides {
                map.insert((*k).to_string(), (*v).to_string());
            }
            let mut block: Vec<u16> = Vec::new();
            for (k, v) in map {
                let entry = format!("{k}={v}");
                block.extend(entry.encode_utf16());
                block.push(0);
            }
            block.push(0);
            block
        }
    }
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

    #[test]
    fn navigation_guard_exact_origin() {
        assert!(is_allowed_navigation("http://127.0.0.1:8756/", 8756));
        assert!(is_allowed_navigation("http://127.0.0.1:8756", 8756));
        assert!(is_allowed_navigation("http://127.0.0.1:8756/api/meta", 8756));
        assert!(is_allowed_navigation("about:blank", 8756));
        assert!(!is_allowed_navigation(
            "http://127.0.0.1:8756@evil.example/",
            8756
        ));
        assert!(!is_allowed_navigation("http://evil.example/", 8756));
        assert!(!is_allowed_navigation("https://127.0.0.1:8756/", 8756));
        assert!(!is_allowed_navigation("http://127.0.0.1:9999/", 8756));
        assert!(!is_allowed_navigation("http://localhost:8756/", 8756));
    }

    /// R2-7: fake child keeps stdout open (no READY) → wait hits deadline.
    #[cfg(unix)]
    #[test]
    fn ready_deadline_while_stdout_open() {
        use std::io::Write;
        use std::os::unix::net::UnixStream;
        use std::time::{Duration, Instant};

        // UnixStream pair: writer held open so reader never gets EOF.
        let (mut writer, reader) = UnixStream::pair().expect("pair");
        writer
            .write_all(b"not-ready-yet\n")
            .expect("write preamble");
        let _hold = writer; // keep write end open

        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("t.log");
        let (rx, join) = spawn_stdout_drain(reader, log);
        let deadline = Instant::now() + Duration::from_millis(400);
        let started = Instant::now();
        let err = wait_for_ready_from_drain(rx, join, || Ok(None), deadline).unwrap_err();
        assert!(
            err.to_string().contains("hết thời gian") || matches!(err, SidecarError::ReadyTimeout),
            "got {err}"
        );
        assert!(started.elapsed() < Duration::from_secs(2));
    }

    /// R2-7: after READY is delivered, drain thread keeps reading (no broken-pipe
    /// from dropping the startup channel mid-stream).
    #[cfg(unix)]
    #[test]
    fn drain_continues_after_ready() {
        use std::io::Write;
        use std::os::unix::net::UnixStream;
        use std::time::{Duration, Instant};

        let (mut writer, reader) = UnixStream::pair().expect("pair");
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("t.log");
        let (rx, join) = spawn_stdout_drain(reader, log.clone());

        // Emit READY then more log lines.
        writer
            .write_all(b"VITRANSCRIPT_READY http://127.0.0.1:8765\n")
            .unwrap();
        writer
            .write_all(b"INFO: uvicorn running after ready\n")
            .unwrap();
        writer.flush().unwrap();

        let deadline = Instant::now() + Duration::from_secs(2);
        let (port, handle) = wait_for_ready_from_drain(rx, join, || Ok(None), deadline).unwrap();
        assert_eq!(port, 8765);

        // More output after READY must still land in the log (reader still alive).
        writer.write_all(b"post-ready-model-output\n").unwrap();
        writer.flush().unwrap();
        drop(writer); // EOF so drain exits
        let _ = handle.join();

        let body = std::fs::read_to_string(&log).unwrap_or_default();
        assert!(
            body.contains("post-ready-model-output"),
            "log missing post-READY bytes: {body:?}"
        );
        assert!(body.contains("uvicorn running after ready"));
    }

    /// R2-7: Unix process group kill reaps leader + descendant (sleep grandchild).
    #[cfg(unix)]
    #[test]
    fn unix_process_group_kills_descendant() {
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        use std::thread;
        use std::time::Duration;

        // Shell becomes group leader; spawns a sleep descendant.
        let mut child = Command::new("bash")
            .args(["-c", "sleep 120 & echo $!; wait"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .process_group(0)
            .spawn()
            .expect("spawn bash");
        let pgid = child.id() as i32;
        let mut stdout = child.stdout.take().unwrap();
        let mut buf = String::new();
        let _ = std::io::Read::read_to_string(&mut stdout, &mut buf);
        let descendant: Option<i32> = buf.trim().parse().ok();

        unix_kill_pg(pgid, 15);
        thread::sleep(Duration::from_millis(200));
        unix_kill_pg(pgid, 9);
        let _ = child.kill();
        let _ = child.wait();

        if let Some(dpid) = descendant {
            extern "C" {
                fn kill(pid: i32, sig: i32) -> i32;
            }
            thread::sleep(Duration::from_millis(100));
            let alive = unsafe { kill(dpid, 0) == 0 };
            assert!(!alive, "descendant {dpid} should be dead after group kill");
        }
    }
}
