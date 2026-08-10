#!/usr/bin/env bash
# Build Linux desktop (AppImage + deb). Ubuntu 22.04 baseline for release.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PATH="${HOME}/.hermes/bin:${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

TRIPLE="$(rustc --print host-tuple)"
echo "host triple: ${TRIPLE}"
case "${TRIPLE}" in
  x86_64-unknown-linux-gnu) ;;
  *) echo "WARN: unexpected linux triple ${TRIPLE}" >&2 ;;
esac

echo "==> sidecar (onefile)"
bash desktop/scripts/build-sidecar.sh onefile

SIDECAR_SRC="desktop/pyinstaller/dist/vitranscript-sidecar"
if [[ ! -x "${SIDECAR_SRC}" ]]; then
  echo "ERROR: missing ${SIDECAR_SRC}" >&2
  exit 1
fi
SRC_SHA="$(sha256sum "${SIDECAR_SRC}" | awk '{print $1}')"

STAGE_DIR="desktop/src-tauri/binaries"
mkdir -p "${STAGE_DIR}"
STAGED="${STAGE_DIR}/vitranscript-sidecar-${TRIPLE}"
# Remove stale staged binaries for this host
rm -f "${STAGE_DIR}/vitranscript-sidecar-${TRIPLE}" \
      "${STAGE_DIR}/vitranscript-sidecar-${TRIPLE}.exe" 2>/dev/null || true
cp -f "${SIDECAR_SRC}" "${STAGED}"
chmod +x "${STAGED}"
ST_SHA="$(sha256sum "${STAGED}" | awk '{print $1}')"
if [[ "${SRC_SHA}" != "${ST_SHA}" ]]; then
  echo "ERROR: staged checksum mismatch" >&2
  exit 1
fi
echo "staged ${STAGED} sha256=${ST_SHA}"

echo "==> cargo tauri build (linux)"
cargo tauri build --manifest-path desktop/src-tauri/Cargo.toml \
  --no-sign \
  --config desktop/src-tauri/tauri.linux.conf.json

echo "==> artifacts"
find desktop/src-tauri/target/release/bundle -type f 2>/dev/null | while read -r f; do
  echo "$(sha256sum "$f")"
done
echo "build-linux done"
