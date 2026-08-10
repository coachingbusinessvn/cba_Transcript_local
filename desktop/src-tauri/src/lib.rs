//! Library surface for unit tests without launching the Tauri event loop.
pub mod sidecar;

// Re-export pure helpers used by tests / main.
pub use sidecar::{
    parse_ready_line, sidecar_binary_name_for_triple, validate_health_json, ReadyParser,
};
