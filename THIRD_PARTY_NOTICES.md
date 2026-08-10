# Third-party notices — ViTranscript Desktop

This document lists third-party components that may be distributed with the
ViTranscript desktop sidecar / installer. Model weights are **not** bundled;
they download on first use into the user data directory.

## FFmpeg / FFprobe

- **Component:** `ffmpeg`, `ffprobe` binaries
- **Source package at build:** `static-ffmpeg` (PyPI) resolves platform
  executables used by the build scripts (`desktop/scripts/build-sidecar.*`).
- **License gate (build-time):** `build-sidecar.sh` / `build-sidecar.ps1` run
  `ffmpeg -version`, parse the **version line** and full **configuration**
  flags, classify the binary as **GPL** or **LGPL** (fail the build if
  `--enable-nonfree` is present, or if version/configuration cannot be audited).
  Results are written to `desktop/pyinstaller/dist/sidecar-manifest.json` under
  `ffmpeg.ffmpeg_version_line`, `ffmpeg.ffmpeg_configuration`,
  `ffmpeg.ffmpeg_license`, and SHA-256 digests. **Do not ship an artifact
  whose manifest lacks these fields.**
- **Distribution duties:**
  - **LGPL** build: you may distribute the binary with this notice and offer
    corresponding source for FFmpeg under LGPL terms.
  - **GPL** build: the combined work’s distribution obligations follow GPL for
    the FFmpeg portion; ship GPL license text and corresponding source offer as
    required by the FFmpeg project for that build.
- **Runtime:** when `sys.frozen`, `app.media` prefers the pair bundled under
  `ffmpeg/` inside the PyInstaller archive; development builds may use system
  PATH or the `static-ffmpeg` package fetch.

### How to re-audit after a build

```bash
# After desktop/scripts/build-sidecar.sh (or .ps1):
python3 -c "import json;print(json.load(open('desktop/pyinstaller/dist/sidecar-manifest.json'))['ffmpeg'])"
```

Releasers must paste the actual `ffmpeg_version_line`, `ffmpeg_license`, and
SHA-256 from the manifest of the **published** artifact into release notes.

### Provenance note

Exact version/configuration vary by OS/arch and by the `static-ffmpeg` wheel
revision. There is **no** fixed “always LGPL” claim — only the audited
`ffmpeg_license` field in the sidecar manifest for that build is authoritative.

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
