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

echo "==> resolve ffmpeg/ffprobe for bundle"
uv run python - <<'PY'
import json, hashlib, platform, sys
from pathlib import Path
import static_ffmpeg.run as sfr

ff, fp = sfr.get_or_fetch_platform_executables_else_raise()
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
meta = {
    "ffmpeg_path": ff,
    "ffprobe_path": fp,
    "ffmpeg_sha256": sha(ff),
    "ffprobe_sha256": sha(fp),
    "os": platform.system(),
    "arch": platform.machine(),
    "python": sys.version.split()[0],
}
out_dir = Path("desktop/pyinstaller")
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "_ffmpeg_resolve.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
# Paths only — no progress text (static_ffmpeg may print to stdout)
(out_dir / "_ffmpeg.path").write_text(ff, encoding="utf-8")
(out_dir / "_ffprobe.path").write_text(fp, encoding="utf-8")
print("OK resolved ffmpeg", ff, file=sys.stderr)
print("OK resolved ffprobe", fp, file=sys.stderr)
PY
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
  echo "==> self-test-native: ${bin}"
  "${bin}" --self-test-native
}

if [[ "$MODE" == "onedir" || "$MODE" == "both" ]]; then
  build_mode onedir
  ONEDIR_BIN="${DIST_DIR}/vitranscript-sidecar/vitranscript-sidecar"
  if [[ ! -x "${ONEDIR_BIN}" ]]; then
    # Windows layout may differ; on Linux this is the path
    ONEDIR_BIN="${DIST_DIR}/vitranscript-sidecar/vitranscript-sidecar"
  fi
  if [[ -x "${ONEDIR_BIN}" ]]; then
    run_self_test "${ONEDIR_BIN}"
  else
    echo "WARN: onedir binary not executable at ${ONEDIR_BIN}" >&2
  fi
fi

if [[ "$MODE" == "onefile" || "$MODE" == "both" ]]; then
  build_mode onefile
  ONEFILE_BIN="${DIST_DIR}/vitranscript-sidecar"
  if [[ -x "${ONEFILE_BIN}" ]]; then
    run_self_test "${ONEFILE_BIN}"
  else
    echo "WARN: onefile binary not executable at ${ONEFILE_BIN}" >&2
  fi
fi

# Write manifest
uv run python - <<'PY'
import hashlib, json, platform, sys
from pathlib import Path
from datetime import datetime, timezone

root = Path(".")
dist = root / "desktop/pyinstaller/dist"
onefile = dist / "vitranscript-sidecar"
onedir = dist / "vitranscript-sidecar" / "vitranscript-sidecar"
ff_meta = {}
p = root / "desktop/pyinstaller/_ffmpeg_resolve.json"
if p.is_file():
    ff_meta = json.loads(p.read_text(encoding="utf-8"))

def sha(path: Path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"path": str(path), "size": path.stat().st_size, "sha256": h.hexdigest()}

manifest = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "os": platform.system(),
    "arch": platform.machine(),
    "python": sys.version.split()[0],
    "ffmpeg": ff_meta,
    "onefile": sha(onefile) if onefile.is_file() else None,
    "onedir": sha(onedir) if onedir.is_file() else None,
}
out = dist / "sidecar-manifest.json"
out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Wrote", out)
print(json.dumps(manifest, indent=2))
PY

echo "==> build-sidecar done (mode=${MODE})"
