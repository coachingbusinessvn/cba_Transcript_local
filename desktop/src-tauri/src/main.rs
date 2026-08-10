//! ViTranscript Tauri shell — spawn Python sidecar, native window after health.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod native;

use native::{emit_paths_to_main, pick_local_files, start_local_job, AppState};
use parking_lot::Mutex;
use vitranscript_lib::sidecar::{self, resolve_sidecar_path, start_and_ready};
use std::path::PathBuf;
use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    Manager, RunEvent, WindowEvent,
};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

fn data_log_dir() -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".into()))
            .join("Library/Application Support/ViTranscript/logs")
    }
    #[cfg(target_os = "windows")]
    {
        PathBuf::from(std::env::var("APPDATA").unwrap_or_else(|_| ".".into()))
            .join("ViTranscript")
            .join("logs")
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
            let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
            format!("{home}/.local/share")
        });
        PathBuf::from(base).join("ViTranscript").join("logs")
    }
}

fn graceful_shutdown(state: &AppState) {
    let mut guard = state.sidecar.lock();
    if let Some(ref mut sc) = *guard {
        let _ = sc.request_shutdown_http();
        sc.wait_exit_or_kill(std::time::Duration::from_secs(sidecar::SHUTDOWN_WAIT_SECS));
    }
    *guard = None;
}

fn main() {
    let app_state = Arc::new(AppState {
        sidecar: Mutex::new(None),
        grants: native::GrantSet::default(),
    });
    let state_for_setup = app_state.clone();
    let state_for_events = app_state.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(app_state.clone())
        .invoke_handler(tauri::generate_handler![pick_local_files, start_local_job])
        .setup(move |app| {
            let log_dir = data_log_dir();
            let _ = std::fs::create_dir_all(&log_dir);

            let current = std::env::current_exe().map_err(|e| e.to_string())?;
            let binary = match resolve_sidecar_path(&current) {
                Ok(p) => p,
                Err(e) => {
                    let triple = env!("TARGET_TRIPLE");
                    let name = sidecar::sidecar_binary_name_for_triple(triple);
                    let staged = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                        .join("binaries")
                        .join(&name);
                    if staged.is_file() {
                        staged
                    } else {
                        eprintln!("sidecar missing: {e}; staged={staged:?}");
                        let _ = app
                            .dialog()
                            .message(format!(
                                "Không khởi động được engine transcript.\n{e}\nLog: {}",
                                log_dir.join("sidecar.log").display()
                            ))
                            .title("ViTranscript")
                            .blocking_show();
                        std::process::exit(1);
                    }
                }
            };

            let sc = match start_and_ready(&binary, &log_dir) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("sidecar startup failed: {e}");
                    let _ = app
                        .dialog()
                        .message(format!(
                            "Không khởi động được engine transcript.\n{e}\nLog: {}",
                            log_dir.join("sidecar.log").display()
                        ))
                        .title("ViTranscript")
                        .blocking_show();
                    std::process::exit(1);
                }
            };

            let url = sc.ready_url.clone();
            *state_for_setup.sidecar.lock() = Some(sc);

            let window = tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::External(url.parse().unwrap()),
            )
            .title("ViTranscript")
            .inner_size(1100.0, 760.0)
            .min_inner_size(900.0, 650.0)
            .build()?;

            let origin = url.clone();
            let _ = window.on_navigation(move |nav_url| {
                let s = nav_url.as_str();
                s.starts_with(origin.as_str()) || s.starts_with("about:blank")
            });

            let open_i = MenuItem::with_id(app, "open", "Mở…", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Thoát", true, None::<&str>)?;
            let about_i = MenuItem::with_id(app, "about", "Giới thiệu", true, None::<&str>)?;
            let docs_i = MenuItem::with_id(app, "docs", "Tài liệu", true, None::<&str>)?;
            let file_m = Submenu::with_items(
                app,
                "File",
                true,
                &[&open_i, &PredefinedMenuItem::separator(app)?, &quit_i],
            )?;
            let help_m = Submenu::with_items(app, "Trợ giúp", true, &[&about_i, &docs_i])?;
            let menu = Menu::with_items(app, &[&file_m, &help_m])?;
            app.set_menu(menu)?;

            let state_menu = state_for_setup.clone();
            app.on_menu_event(move |app, event| match event.id().as_ref() {
                "open" => {
                    let app2 = app.clone();
                    let st = state_menu.clone();
                    std::thread::spawn(move || {
                        let (tx, rx) = std::sync::mpsc::channel();
                        app2.dialog()
                            .file()
                            .add_filter("Media", native::MEDIA_EXTENSIONS)
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
                        if let Ok(paths) = rx.recv() {
                            let mut granted = Vec::new();
                            for p in paths {
                                if PathBuf::from(&p).is_absolute() {
                                    st.grants.grant(&p);
                                    granted.push(p);
                                }
                            }
                            emit_paths_to_main(&app2, granted);
                        }
                    });
                }
                "quit" => {
                    graceful_shutdown(&state_menu);
                    app.exit(0);
                }
                "about" => {
                    let _ = app
                        .dialog()
                        .message(
                            "ViTranscript 0.1.0\nChuyển audio/video thành transcript tiếng Việt (local-first).",
                        )
                        .title("Giới thiệu")
                        .blocking_show();
                }
                "docs" => {
                    let _ = app.opener().open_url(
                        "https://github.com/innercoach/cba_Transcript_local",
                        None::<&str>,
                    );
                }
                _ => {}
            });

            // File drop: grant paths + emit to webview
            let st_drop = state_for_setup.clone();
            let app_drop = app.handle().clone();
            window.on_window_event(move |event| {
                if let WindowEvent::DragDrop(tauri::DragDropEvent::Drop { paths, position: _ }) =
                    event
                {
                    let strs: Vec<String> = paths
                        .iter()
                        .map(|p| p.to_string_lossy().to_string())
                        .collect();
                    let granted = native::grant_dropped_paths(&st_drop, strs);
                    emit_paths_to_main(&app_drop, granted);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(move |app_handle, event| match event {
            RunEvent::WindowEvent {
                label,
                event: WindowEvent::CloseRequested { api, .. },
                ..
            } if label == "main" => {
                api.prevent_close();
                graceful_shutdown(&state_for_events);
                app_handle.exit(0);
            }
            RunEvent::Exit => {
                graceful_shutdown(&state_for_events);
            }
            _ => {}
        });
}
