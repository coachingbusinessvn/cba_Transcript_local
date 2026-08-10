#!/usr/bin/env bash
# Build macOS desktop (.app + .dmg). Native arch only (no cross).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PATH="${HOME}/.hermes/bin:${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

TRIPLE="$(rustc --print host-tuple)"
echo "host triple: ${TRIPLE}"

echo "==> sidecar (onefile)"
bash desktop/scripts/build-sidecar.sh onefile

SIDECAR_SRC="desktop/pyinstaller/dist/vitranscript-sidecar"
if [[ ! -x "${SIDECAR_SRC}" ]]; then
  echo "ERROR: missing ${SIDECAR_SRC}" >&2
  exit 1
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
cargo tauri build --manifest-path desktop/src-tauri/Cargo.toml \
  --no-sign \
  --config desktop/src-tauri/tauri.macos.conf.json

echo "==> artifacts"
find desktop/src-tauri/target/release/bundle -type f 2>/dev/null | while read -r f; do
  echo "$(shasum -a 256 "$f")"
done
echo "build-macos done"
