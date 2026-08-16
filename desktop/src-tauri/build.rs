fn main() {
    let triple = std::env::var("TARGET").unwrap_or_else(|_| "unknown".into());
    println!("cargo:rustc-env=TARGET_TRIPLE={triple}");
    // Only run tauri-build when the gui feature is enabled.
    #[cfg(feature = "gui")]
    {
        // Register app commands so ACL can allow them without core:default (R2-6).
        tauri_build::try_build(
            tauri_build::Attributes::new().app_manifest(
                tauri_build::AppManifest::new()
                    .commands(&["pick_local_files", "start_local_job"]),
            ),
        )
        .expect("tauri-build failed");
    }
}
