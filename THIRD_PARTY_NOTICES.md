# Third-party notices — ViTranscript Desktop

This document lists third-party components that may be distributed with the
ViTranscript desktop sidecar / installer. Model weights are **not** bundled;
they download on first use into the user data directory.

## FFmpeg / FFprobe

- **Component:** `ffmpeg`, `ffprobe` binaries
- **Source package at build:** `static-ffmpeg` (PyPI) resolves platform
  executables used by the build scripts (`desktop/scripts/build-sidecar.*`).
- **License:** FFmpeg is typically LGPL/GPL depending on build configuration.
  The exact build flags and version of the binaries resolved on each CI host
  are recorded in `desktop/pyinstaller/dist/sidecar-manifest.json` (ffmpeg
  SHA-256 + path metadata) at build time.
- **Runtime:** when `sys.frozen`, `app.media` prefers the pair bundled under
  `ffmpeg/` inside the PyInstaller archive; development builds may use system
  PATH or the `static-ffmpeg` package fetch.

### Provenance snapshot (Linux x86_64 build host, 2026-08-10)

- **Version string:** `ffmpeg version n8.0.1-48-g0592be14ff-20260116` (static-ffmpeg resolve)
- **SHA-256 (ffmpeg):** `ff45e18f5823f3036e419b22de5582ee5c956907910465e94e6d56df0aebb470`
- **SHA-256 (ffprobe):** `9960ffd53be2a73bf2d33849ab792ba405e3701a996917c6f6b5d28bc9354296`
- **Resolved via:** PyPI `static-ffmpeg` → `static_ffmpeg/bin/linux/{ffmpeg,ffprobe}`
- Releasers must re-record hashes from `desktop/pyinstaller/dist/sidecar-manifest.json`
  for each published artifact.

## Native ML runtimes (sidecar)

| Package | Role | Typical license (upstream) |
|---|---|---|
| `faster-whisper` / CTranslate2 | ASR inference | MIT / MPL-2.0 (CTranslate2) |
| `onnxruntime` | ONNX runtime (punctuation, diarization helpers) | MIT |
| `sherpa-onnx` + `sherpa-onnx-core` | Speaker diarization | Apache-2.0 |
| `tokenizers` | Tokenization (punctuation model) | Apache-2.0 |
| `av` (PyAV) | Media helpers | BSD-3-Clause |
| `static-ffmpeg` | Build-time ffmpeg fetch helper | Apache-2.0 (package); ffmpeg separate |

See each package's upstream repository for the authoritative license text.

## Application stack

| Package | Role |
|---|---|
| FastAPI / Starlette / Uvicorn | Local HTTP API |
| python-docx / openpyxl | Export DOCX/XLSX |
| rapidfuzz | Glossary fuzzy match |
| huggingface-hub | Model download (first run) |
| numpy | Array IO for diarization |
| PyInstaller | Sidecar packaging tool (build only) |
| Tauri / Rust crates | Desktop shell (see `desktop/src-tauri`) |

## Forbidden dependencies

The project **must not** ship PyTorch or TensorFlow. Build scripts refuse an
environment that has those distributions installed.

## Models (not redistributed in installer)

- PhoWhisper / Whisper CTranslate2 checkpoints (Hugging Face)
- ViBERT-CAPU ONNX punctuation model
- pyannote segmentation + eres2net ONNX (diarization)

Downloaded into OS data dir (`ViTranscript/models`, `punctuation`, `diarization`)
on first use; subject to their respective model licenses (see app UI / README).
