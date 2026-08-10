//! Native file bridge: picker, grant-set, start_local_job, drag-drop helpers.

use parking_lot::Mutex;
use serde::Serialize;
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Arc;
use tauri::{AppHandle, Emitter, Manager, State};
use vitranscript_lib::job_options::LocalJobOptions;
use vitranscript_lib::sidecar::SidecarState;

/// Extensions matching app.media AUDIO_EXTS | VIDEO_EXTS
pub const MEDIA_EXTENSIONS: &[&str] = &[
    "mp3", "m4a", "wav", "aac", "flac", "ogg", "wma", "opus", "mov", "mp4", "mkv", "avi", "webm",
    "m4v",
];

#[derive(Default)]
pub struct GrantSet {
    paths: Mutex<HashSet<String>>,
}

impl GrantSet {
    pub fn grant(&self, path: &str) {
        self.paths.lock().insert(path.to_string());
    }

    pub fn contains(&self, path: &str) -> bool {
        self.paths.lock().contains(path)
    }

    pub fn grant_many(&self, paths: &[String]) {
        let mut g = self.paths.lock();
        for p in paths {
            g.insert(p.clone());
        }
    }
}

pub struct AppState {
    pub sidecar: Mutex<Option<SidecarState>>,
    pub grants: GrantSet,
}

#[derive(Debug, Serialize)]
pub struct LocalJobResponse {
    pub status: u16,
    pub body: String,
}

#[tauri::command]
pub async fn pick_local_files(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let (tx, rx) = std::sync::mpsc::channel();
    app.dialog()
        .file()
        .add_filter("Media", MEDIA_EXTENSIONS)
        .set_title("Chọn file audio/video")
        .pick_files(move |files| {
            let paths = files
                .map(|list| {
                    list.into_iter()
                        .filter_map(|f| f.into_path().ok())
                        .map(|p| p.to_string_lossy().to_string())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            let _ = tx.send(paths);
        });
    let paths = rx.recv().map_err(|e| e.to_string())?;
    // Require absolute; grant original paths (no canonicalize — backend rejects symlink)
    let mut out = Vec::new();
    for p in paths {
        let pb = PathBuf::from(&p);
        if !pb.is_absolute() {
            continue;
        }
        state.grants.grant(&p);
        out.push(p);
    }
    Ok(out)
}

#[tauri::command]
pub async fn start_local_job(
    state: State<'_, Arc<AppState>>,
    path: String,
    options: LocalJobOptions,
) -> Result<LocalJobResponse, String> {
    if !state.grants.contains(&path) {
        return Err("path chưa được grant bởi native picker/drop".into());
    }
    let (url, token) = {
        let guard = state.sidecar.lock();
        let sc = guard.as_ref().ok_or("sidecar chưa sẵn sàng")?;
        (
            format!("{}/api/jobs/local", sc.ready_url),
            sc.token.clone(),
        )
    };
    let body = serde_json::json!({
        "path": path,
        "model": options.model,
        "language": options.language,
        "diarize": options.diarize,
        "punctuate": options.punctuate,
        "num_speakers": options.num_speakers,
        "glossary": options.glossary,
    });
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(std::time::Duration::from_secs(3))
        // No whole-pipeline timeout — request only enqueues
        .timeout_read(std::time::Duration::from_secs(30))
        .build();
    match agent
        .post(&url)
        .set("X-ViTranscript-Token", &token)
        .set("Content-Type", "application/json")
        .send_json(body)
    {
        Ok(resp) => {
            let status = resp.status();
            let text = resp.into_string().unwrap_or_default();
            Ok(LocalJobResponse {
                status,
                body: text,
            })
        }
        Err(ureq::Error::Status(code, resp)) => {
            let text = resp.into_string().unwrap_or_default();
            Ok(LocalJobResponse {
                status: code,
                body: text,
            })
        }
        Err(e) => Err(format!("local job request failed: {e}")),
    }
}

/// Grant paths from native drag-drop (files only; caller filters directories).
pub fn grant_dropped_paths(state: &AppState, paths: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    for p in paths {
        let pb = PathBuf::from(&p);
        if !pb.is_absolute() || !pb.is_file() {
            continue;
        }
        let ext = pb
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_ascii_lowercase())
            .unwrap_or_default();
        if !MEDIA_EXTENSIONS.iter().any(|x| *x == ext) {
            continue;
        }
        state.grants.grant(&p);
        out.push(p);
    }
    out
}

pub fn emit_paths_to_main(app: &AppHandle, paths: Vec<String>) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.emit("native-files", paths);
    }
}
