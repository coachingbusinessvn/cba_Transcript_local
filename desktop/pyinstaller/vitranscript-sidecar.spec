# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onedir (chẩn đoán) + onefile (release) từ cùng Analysis.

Usage:
  pyinstaller --clean --noconfirm vitranscript-sidecar.spec -- --mode onedir
  pyinstaller --clean --noconfirm vitranscript-sidecar.spec -- --mode onefile
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all

# --- mode: env VITRANSCRIPT_PYI_MODE or argv after -- ---
_mode = os.environ.get("VITRANSCRIPT_PYI_MODE", "onefile")
if "--" in sys.argv:
    _after = sys.argv[sys.argv.index("--") + 1 :]
    for i, a in enumerate(_after):
        if a == "--mode" and i + 1 < len(_after):
            _mode = _after[i + 1]
        elif a.startswith("--mode="):
            _mode = a.split("=", 1)[1]
else:
    for i, a in enumerate(sys.argv):
        if a == "--mode" and i + 1 < len(sys.argv):
            _mode = sys.argv[i + 1]
        elif a.startswith("--mode="):
            _mode = a.split("=", 1)[1]
if _mode not in ("onefile", "onedir"):
    raise SystemExit(f"Unknown --mode {_mode!r}; use onedir|onefile")
print(f"PyInstaller spec mode={_mode}", file=sys.stderr)

# SPECPATH is injected by PyInstaller when executing the spec
SPECDIR = Path(globals().get("SPECPATH") or os.environ.get("SPEC", Path(sys.argv[0]).parent))
if not (SPECDIR / "sidecar_entry.py").is_file():
    # Fallback: this file lives in desktop/pyinstaller/
    SPECDIR = Path(os.path.abspath(SPEC if "SPEC" in dir() else __file__)).parent  # type: ignore[name-defined]
ROOT = SPECDIR.parent.parent  # desktop/pyinstaller -> repo root
ENTRY = str(SPECDIR / "sidecar_entry.py")
print(f"SPECDIR={SPECDIR} ROOT={ROOT} ENTRY={ENTRY}", file=sys.stderr)

# collect_all for native-heavy packages
_COLLECT_PKGS = (
    "ctranslate2",
    "onnxruntime",
    "sherpa_onnx",
    "tokenizers",
    "faster_whisper",
    "av",
    "static_ffmpeg",
)

datas: list = []
binaries: list = []
hiddenimports: list = []

for pkg in _COLLECT_PKGS:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"WARN collect_all({pkg}): {e}", file=sys.stderr)

# Explicit dynamic imports
hiddenimports += [
    "ctranslate2",
    "onnxruntime",
    "onnxruntime.capi._pybind_state",
    "sherpa_onnx",
    "tokenizers",
    "faster_whisper",
    "faster_whisper.transcribe",
    "av",
    "static_ffmpeg",
    "static_ffmpeg.run",
    "app",
    "app.server",
    "app.server_runtime",
    "app.media",
    "app.config",
    "app.pipeline",
    "app.transcribe",
    "app.diarize",
    "app.punctuate",
    "app.glossary",
    "app.segment",
    "app.export",
    "app.checkpoint",
]

# app/static
static_dir = ROOT / "app" / "static"
if static_dir.is_dir():
    datas.append((str(static_dir), "app/static"))


def _native_files_from_dist(dist_name: str) -> list[tuple[str, str]]:
    """Collect .so/.dylib/.dll/.pyd from a distribution (for sherpa-onnx-core)."""
    out: list[tuple[str, str]] = []
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        print(f"WARN: distribution {dist_name!r} not found", file=sys.stderr)
        return out
    files = dist.files or []
    locate = dist.locate_file
    for f in files:
        s = str(f)
        if s.endswith((".so", ".dylib", ".dll", ".pyd")) or ".so." in s:
            src = Path(locate(f))
            if src.is_file():
                # Keep relative parent under package layout
                parent = str(Path(s).parent)
                if parent == ".":
                    parent = "."
                out.append((str(src), parent))
    return out


for dist_name in ("sherpa-onnx", "sherpa-onnx-core"):
    binaries += _native_files_from_dist(dist_name)

# Bundle ffmpeg + ffprobe resolved at build time into ffmpeg/
_ffmpeg_bin_env = os.environ.get("VITRANSCRIPT_BUNDLE_FFMPEG")
_ffprobe_bin_env = os.environ.get("VITRANSCRIPT_BUNDLE_FFPROBE")
if _ffmpeg_bin_env and Path(_ffmpeg_bin_env).is_file():
    binaries.append((_ffmpeg_bin_env, "ffmpeg"))
if _ffprobe_bin_env and Path(_ffprobe_bin_env).is_file():
    binaries.append((_ffprobe_bin_env, "ffmpeg"))

# Deduplicate (src, dest) pairs
def _dedupe(items: list) -> list:
    seen: set = set()
    out = []
    for it in items:
        key = tuple(it) if isinstance(it, (list, tuple)) else it
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


datas = _dedupe(datas)
binaries = _dedupe(binaries)
hiddenimports = sorted(set(hiddenimports))

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "transformers"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries if _mode == "onefile" else [],
    a.zipfiles if _mode == "onefile" else [],
    a.datas if _mode == "onefile" else [],
    [],
    name="vitranscript-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=(_mode == "onedir"),
)

if _mode == "onedir":
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="vitranscript-sidecar",
    )
