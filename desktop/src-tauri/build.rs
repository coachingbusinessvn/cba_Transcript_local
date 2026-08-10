fn main() {
    let triple = std::env::var("TARGET").unwrap_or_else(|_| "unknown".into());
    println!("cargo:rustc-env=TARGET_TRIPLE={triple}");
    // Only run tauri-build when the gui feature is enabled.
    #[cfg(feature = "gui")]
    tauri_build::build();
}
