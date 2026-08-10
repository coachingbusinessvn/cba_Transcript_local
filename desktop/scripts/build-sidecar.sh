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

echo "==> resolve ffmpeg/ffprobe for bundle + license audit"
uv run python - <<'PY'
import json, hashlib, platform, re, subprocess, sys
from pathlib import Path
import static_ffmpeg.run as sfr

ff, fp = sfr.get_or_fetch_platform_executables_else_raise()

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def audit_ffmpeg(path: str) -> dict:
    """Run ffmpeg -version; require version + configuration; classify GPL/LGPL."""
    try:
        proc = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as e:
        print(f"ERROR: cannot execute ffmpeg for audit: {e}", file=sys.stderr)
        sys.exit(1)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode not in (0,):
        # ffmpeg -version usually exits 0; still parse if output present
        if "ffmpeg version" not in text.lower() and "version" not in text.lower():
            print(f"ERROR: ffmpeg -version failed (code={proc.returncode})", file=sys.stderr)
            print(text[:2000], file=sys.stderr)
            sys.exit(1)
    version_line = ""
    configuration = ""
    for line in text.splitlines():
        ls = line.strip()
        if not version_line and ls.lower().startswith("ffmpeg version"):
            version_line = ls
        if ls.lower().startswith("configuration:"):
            configuration = ls.split(":", 1)[1].strip() if ":" in ls else ls
    if not version_line:
        print("ERROR: could not parse ffmpeg version line from -version output", file=sys.stderr)
        print(text[:2000], file=sys.stderr)
        sys.exit(1)
    if not configuration:
        print("ERROR: could not parse ffmpeg configuration line — cannot audit license", file=sys.stderr)
        print(text[:2000], file=sys.stderr)
        sys.exit(1)
    cfg_l = configuration.lower()
    # GPL if --enable-gpl present (and not only disabled); LGPL otherwise for typical static builds.
    if re.search(r"--enable-gpl\b", cfg_l) and not re.search(r"--disable-gpl\b", cfg_l):
        license_kind = "GPL"
    elif re.search(r"--enable-version3\b", cfg_l) and re.search(r"--enable-gpl\b", cfg_l):
        license_kind = "GPL"
    elif re.search(r"--enable-nonfree\b", cfg_l):
        license_kind = "NONFREE"
    else:
        license_kind = "LGPL"
    if license_kind == "NONFREE":
        print("ERROR: ffmpeg build is NONFREE — cannot distribute", file=sys.stderr)
        sys.exit(1)
    return {
        "version_line": version_line,
        "configuration": configuration,
        "license": license_kind,
        "version_exit_code": proc.returncode,
    }

audit = audit_ffmpeg(ff)
meta = {
    # Do not store absolute personal paths in committed artifacts — basename only for display;
    # full path kept only for local build env files.
    "ffmpeg_basename": Path(ff).name,
    "ffprobe_basename": Path(fp).name,
    "ffmpeg_path": ff,
    "ffprobe_path": fp,
    "ffmpeg_sha256": sha(ff),
    "ffprobe_sha256": sha(fp),
    "ffmpeg_version_line": audit["version_line"],
    "ffmpeg_configuration": audit["configuration"],
    "ffmpeg_license": audit["license"],
    "source_package": "static-ffmpeg (PyPI)",
    "os": platform.system(),
    "arch": platform.machine(),
    "python": sys.version.split()[0],
}
out_dir = Path("desktop/pyinstaller")
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "_ffmpeg_resolve.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
(out_dir / "_ffmpeg.path").write_text(ff, encoding="utf-8")
(out_dir / "_ffprobe.path").write_text(fp, encoding="utf-8")
print("OK resolved ffmpeg", ff, file=sys.stderr)
print("OK resolved ffprobe", fp, file=sys.stderr)
print("OK ffmpeg license=", audit["license"], file=sys.stderr)
print("OK", audit["version_line"], file=sys.stderr)
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

# Write manifest (no personal absolute paths in published fields)
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

# Fail if ffmpeg license audit missing
if not ff_meta.get("ffmpeg_license") or not ff_meta.get("ffmpeg_version_line"):
    print("ERROR: ffmpeg audit fields missing in _ffmpeg_resolve.json", file=sys.stderr)
    sys.exit(1)
if not ff_meta.get("ffmpeg_configuration"):
    print("ERROR: ffmpeg configuration missing — refuse to publish artifact", file=sys.stderr)
    sys.exit(1)

def sha(path: Path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": h.hexdigest(),
    }

# Public ffmpeg block: strip absolute paths
ff_public = {
    "ffmpeg_basename": ff_meta.get("ffmpeg_basename"),
    "ffprobe_basename": ff_meta.get("ffprobe_basename"),
    "ffmpeg_sha256": ff_meta.get("ffmpeg_sha256"),
    "ffprobe_sha256": ff_meta.get("ffprobe_sha256"),
    "ffmpeg_version_line": ff_meta.get("ffmpeg_version_line"),
    "ffmpeg_configuration": ff_meta.get("ffmpeg_configuration"),
    "ffmpeg_license": ff_meta.get("ffmpeg_license"),
    "source_package": ff_meta.get("source_package", "static-ffmpeg (PyPI)"),
}

manifest = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "os": platform.system(),
    "arch": platform.machine(),
    "python": sys.version.split()[0],
    "ffmpeg": ff_public,
    "onefile": sha(onefile) if onefile.is_file() else None,
    "onedir": sha(onedir) if onedir.is_file() else None,
}
out = dist / "sidecar-manifest.json"
out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Wrote", out)
print(json.dumps(manifest, indent=2))
PY

echo "==> build-sidecar done (mode=${MODE})"
