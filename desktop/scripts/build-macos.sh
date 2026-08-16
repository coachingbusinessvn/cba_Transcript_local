#!/usr/bin/env bash
# Build macOS desktop (.app + .dmg). Native arch only (no cross).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PATH="${HOME}/.hermes/bin:${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

TRIPLE="$(rustc --print host-tuple)"
echo "host triple: ${TRIPLE}"

# Map Python arch → expected Rust triple fragment (fail before stage on mismatch).
PY_MACHINE="$(uv run python -c 'import platform; print(platform.machine())')"
case "${PY_MACHINE}" in
  arm64|aarch64) EXPECT_TRIPLE="aarch64-apple-darwin" ;;
  x86_64|amd64|AMD64) EXPECT_TRIPLE="x86_64-apple-darwin" ;;
  *)
    echo "ERROR: unsupported Python machine=${PY_MACHINE}" >&2
    exit 1
    ;;
esac
if [[ "${TRIPLE}" != "${EXPECT_TRIPLE}" ]]; then
  echo "ERROR: rustc triple (${TRIPLE}) != Python arch triple (${EXPECT_TRIPLE} from machine=${PY_MACHINE})" >&2
  exit 1
fi

echo "==> sidecar (onefile)"
bash desktop/scripts/build-sidecar.sh onefile

SIDECAR_SRC="desktop/pyinstaller/dist/vitranscript-sidecar"
if [[ ! -x "${SIDECAR_SRC}" ]]; then
  echo "ERROR: missing ${SIDECAR_SRC}" >&2
  exit 1
fi

# Verify sidecar binary arch matches triple (file(1) / lipo / Mach-O).
if command -v file >/dev/null 2>&1; then
  FILE_OUT="$(file -b "${SIDECAR_SRC}" || true)"
  echo "sidecar file: ${FILE_OUT}"
  case "${TRIPLE}" in
    aarch64-apple-darwin)
      if ! echo "${FILE_OUT}" | grep -Eiq 'arm64|aarch64'; then
        echo "ERROR: sidecar arch mismatch for ${TRIPLE}: ${FILE_OUT}" >&2
        exit 1
      fi
      ;;
    x86_64-apple-darwin)
      if ! echo "${FILE_OUT}" | grep -Eiq 'x86_64'; then
        echo "ERROR: sidecar arch mismatch for ${TRIPLE}: ${FILE_OUT}" >&2
        exit 1
      fi
      ;;
  esac
fi

SRC_SHA="$(shasum -a 256 "${SIDECAR_SRC}" | awk '{print $1}')"

STAGE_DIR="desktop/src-tauri/binaries"
mkdir -p "${STAGE_DIR}"
STAGED="${STAGE_DIR}/vitranscript-sidecar-${TRIPLE}"
rm -f "${STAGE_DIR}/vitranscript-sidecar-"* 2>/dev/null || true
cp -f "${SIDECAR_SRC}" "${STAGED}"
chmod +x "${STAGED}"
ST_SHA="$(shasum -a 256 "${STAGED}" | awk '{print $1}')"
if [[ "${SRC_SHA}" != "${ST_SHA}" ]]; then
  echo "ERROR: staged checksum mismatch" >&2
  exit 1
fi

echo "==> cargo tauri build (macos)"
# Tauri CLI 2.x does not accept cargo's --manifest-path; run from src-tauri.
(
  cd desktop/src-tauri
  cargo tauri build --no-sign --config tauri.macos.conf.json
)

echo "==> artifacts"
find desktop/src-tauri/target/release/bundle -type f 2>/dev/null | while read -r f; do
  echo "$(shasum -a 256 "$f")"
done
echo "build-macos done"
