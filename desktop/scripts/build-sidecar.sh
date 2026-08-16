#!/usr/bin/env bash
# Build ViTranscript Python sidecar (PyInstaller onedir + onefile).
# ASCII-only for Windows portability notes; this script is bash/Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.hermes/bin:${HOME}/.local/bin:${PATH}"

MODE="${1:-both}"  # onedir | onefile | both

echo "==> uv sync --frozen --group desktop"
uv sync --frozen --group desktop

echo "==> refuse torch/tensorflow in environment"
uv run python - <<'PY'
import importlib.metadata as m
import sys
bad = []
for d in m.distributions():
    name = (d.metadata.get("Name") or "").lower()
    if name in ("torch", "tensorflow", "tensorflow-cpu", "tensorflow-gpu") or name.startswith("torch-"):
        bad.append(name)
if bad:
    print("ERROR: forbidden packages present:", bad, file=sys.stderr)
    sys.exit(1)
print("OK: no torch/tensorflow")
PY

echo "==> resolve ffmpeg/ffprobe for bundle + license audit (shared Python)"
uv run python desktop/scripts/ffmpeg_license_audit.py resolve
export VITRANSCRIPT_BUNDLE_FFMPEG="$(cat desktop/pyinstaller/_ffmpeg.path)"
export VITRANSCRIPT_BUNDLE_FFPROBE="$(cat desktop/pyinstaller/_ffprobe.path)"
echo "BUNDLE ffmpeg=$VITRANSCRIPT_BUNDLE_FFMPEG"
echo "BUNDLE ffprobe=$VITRANSCRIPT_BUNDLE_FFPROBE"

SPEC="desktop/pyinstaller/vitranscript-sidecar.spec"
DIST_DIR="desktop/pyinstaller/dist"
BUILD_DIR="desktop/pyinstaller/build"
mkdir -p "$DIST_DIR" "$BUILD_DIR"

build_mode() {
  local mode="$1"
  echo "==> PyInstaller mode=${mode}"
  export VITRANSCRIPT_PYI_MODE="${mode}"
  uv run pyinstaller \
    --clean --noconfirm \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/${mode}" \
    "$SPEC"

  # Fail only if top-level native packages themselves are missing
  local warn
  warn="$(find "$BUILD_DIR/${mode}" -name 'warn-*.txt' 2>/dev/null | head -1 || true)"
  if [[ -n "${warn}" && -f "${warn}" ]]; then
    if grep -E '^missing module named (ctranslate2|onnxruntime|sherpa_onnx|tokenizers|faster_whisper|av|static_ffmpeg)( |$)' "${warn}" >/dev/null 2>&1; then
      echo "ERROR: native module missing in ${warn}" >&2
      grep -E '^missing module named (ctranslate2|onnxruntime|sherpa_onnx|tokenizers|faster_whisper|av|static_ffmpeg)( |$)' "${warn}" >&2 || true
      exit 1
    fi
  fi
}

run_self_test() {
  local bin="$1"
  if [[ ! -e "${bin}" ]]; then
    echo "ERROR: sidecar binary missing: ${bin}" >&2
    exit 1
  fi
  if [[ ! -x "${bin}" ]]; then
    echo "ERROR: sidecar binary not executable: ${bin}" >&2
    exit 1
  fi
  echo "==> self-test-native: ${bin}"
  "${bin}" --self-test-native
}

if [[ "$MODE" == "onedir" || "$MODE" == "both" ]]; then
  build_mode onedir
  ONEDIR_BIN="${DIST_DIR}/vitranscript-sidecar/vitranscript-sidecar"
  run_self_test "${ONEDIR_BIN}"
fi

if [[ "$MODE" == "onefile" || "$MODE" == "both" ]]; then
  build_mode onefile
  ONEFILE_BIN="${DIST_DIR}/vitranscript-sidecar"
  run_self_test "${ONEFILE_BIN}"
fi

echo "==> write sidecar-manifest.json (shared audit + license gate)"
uv run python desktop/scripts/ffmpeg_license_audit.py write-manifest \
  --mode "${MODE}" \
  --dist "${DIST_DIR}"

echo "==> build-sidecar done (mode=${MODE})"
