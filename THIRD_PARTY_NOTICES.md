# Third-party notices — ViTranscript Desktop

This document lists third-party components that may be distributed with the
ViTranscript desktop sidecar / installer. Model weights are **not** bundled;
they download on first use into the user data directory.

## FFmpeg / FFprobe

- **Component:** `ffmpeg`, `ffprobe` binaries
- **Resolver:** PyPI package `static-ffmpeg` (exact version recorded in the
  sidecar manifest as `ffmpeg.resolver_package_version`). Build scripts call
  the **shared** auditor `desktop/scripts/ffmpeg_license_audit.py` from both
  `build-sidecar.sh` and `build-sidecar.ps1` so classification order cannot drift.
- **Platform download:** `static_ffmpeg` fetches a platform zip from
  `https://github.com/zackees/ffmpeg_bins` (e.g. `.../v8.0/linux.zip`). The
  exact URL, platform key, and revision are written to the manifest fields
  `download_url`, `platform_key`, and `download_revision`.
- **License gate (build-time, fail-closed):**
  1. Run `ffmpeg -version` and parse the **version line** + full **configuration**.
  2. If configuration contains `--enable-nonfree` → **fail immediately**
     (checked **before** GPL/LGPL classification, even when `--enable-gpl` is also set).
  3. Else if `--enable-gpl` (and not `--disable-gpl`) → **GPL**; else **LGPL**.
  4. Stage into `desktop/pyinstaller/dist/ffmpeg-notices/`:
     - license text (`COPYING.GPLv3` or `COPYING.LGPLv2.1`) from
       `desktop/third_party/ffmpeg/`;
     - `SOURCE_OFFER.txt` that embeds the **exact** `ffmpeg_sha256` /
       `ffprobe_sha256` and the download URL/revision.
  5. Refuse to write `sidecar-manifest.json` if license text or source-offer is
     missing, hash-mismatched, or does not reference the audited binary hashes.
- **Manifest fields (authoritative for a build):**
  `ffmpeg_version_line`, `ffmpeg_configuration`, `ffmpeg_license`,
  `ffmpeg_sha256`, `ffprobe_sha256`, `resolver_package_version`,
  `download_url`, `download_revision`, `license_artifacts.*`.
- **Distribution duties:**
  - **LGPL** build: distribute with this notice + staged LGPL text + source offer.
  - **GPL** build: ship GPL license text and corresponding source offer for the
    FFmpeg portion as required for that build.
- **Runtime:** when `sys.frozen`, `app.media` prefers the pair bundled under
  `ffmpeg/` inside the PyInstaller archive; development builds may use system
  PATH or the `static-ffmpeg` package fetch.

### How to re-audit after a build

```bash
# After desktop/scripts/build-sidecar.sh (or .ps1):
python3 -c "import json;print(json.load(open('desktop/pyinstaller/dist/sidecar-manifest.json'))['ffmpeg'])"
ls desktop/pyinstaller/dist/ffmpeg-notices/
```

Releasers must paste the actual `ffmpeg_version_line`, `ffmpeg_license`,
SHA-256 digests, and `download_url` from the **published** artifact manifest
into release notes, and keep `ffmpeg-notices/` next to the binary.

### Provenance note

Exact version/configuration vary by OS/arch and by the `static-ffmpeg` wheel
revision / `ffmpeg_bins` zip revision. There is **no** fixed “always LGPL”
claim — only the audited `ffmpeg_license` field in the sidecar manifest for
that build is authoritative. Bundled license texts live under
`desktop/third_party/ffmpeg/` and are copied into the artifact notices dir.

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
