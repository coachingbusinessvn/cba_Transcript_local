#!/usr/bin/env bash
# Clean Ubuntu 22.04 runtime gate (R2-5 / finding #12).
# Build a minimal runtime image once (networked), then:
#   1) ONLINE full job/export with shared data volume
#   2) OFFLINE same volume with --network none (no apt — packages already in image)
# Failure to isolate network is a hard failure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIDECAR="${1:-$ROOT/desktop/pyinstaller/dist/vitranscript-sidecar}"
WAV="${2:-}"
IMAGE_TAG="${VITRANSCRIPT_E2E_IMAGE:-vitranscript-e2e-runtime:local}"
DOCKERFILE="$ROOT/scripts/docker/e2e-runtime.Dockerfile"

# Resolve to absolute path so docker -v never treats a relative path as a volume name.
abspath() {
  local p="$1"
  if [[ ! -e "${p}" ]]; then
    echo "ERROR: path not found: ${p}" >&2
    return 1
  fi
  # Prefer realpath when available (handles symlinks); fallback for minimal hosts.
  if command -v realpath >/dev/null 2>&1; then
    realpath "${p}"
  else
    echo "$(cd "$(dirname "${p}")" && pwd)/$(basename "${p}")"
  fi
}

if [[ ! -f "${SIDECAR}" ]]; then
  echo "ERROR: sidecar not found: ${SIDECAR}" >&2
  exit 1
fi
# Execute bit must be set on the host BEFORE a read-only mount (cannot chmod :ro).
if [[ ! -x "${SIDECAR}" ]]; then
  chmod +x "${SIDECAR}" || {
    echo "ERROR: cannot set execute bit on sidecar: ${SIDECAR}" >&2
    exit 1
  }
fi
if [[ ! -x "${SIDECAR}" ]]; then
  echo "ERROR: sidecar not executable: ${SIDECAR}" >&2
  exit 1
fi
SIDECAR="$(abspath "${SIDECAR}")"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker required for clean Ubuntu runtime gate" >&2
  exit 1
fi
if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "ERROR: missing Dockerfile: ${DOCKERFILE}" >&2
  exit 1
fi

if [[ -z "${WAV}" || ! -f "${WAV}" ]]; then
  WAV="$(mktemp /tmp/vitranscript-e2e-XXXX.wav)"
  bash "$ROOT/scripts/gen_test_audio_linux.sh" "${WAV}"
fi
WAV="$(abspath "${WAV}")"

DATA_VOL="vitranscript-e2e-data-$$"
docker volume create "${DATA_VOL}" >/dev/null

cleanup() {
  docker volume rm -f "${DATA_VOL}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> build minimal Ubuntu 22.04 runtime image (${IMAGE_TAG})"
docker build -t "${IMAGE_TAG}" -f "${DOCKERFILE}" "$ROOT/scripts/docker"

run_in_container() {
  # Args: extra docker run flags (e.g. --network none)
  # Mount sidecar :ro — execute bit already set on host; do NOT chmod inside container.
  docker run --rm \
    "$@" \
    -v "${SIDECAR}:/sidecar:ro" \
    -v "${WAV}:/sample.wav:ro" \
    -v "${DATA_VOL}:/data" \
    -v "$ROOT/scripts/e2e_sidecar_linux.py:/e2e.py:ro" \
    -e XDG_DATA_HOME=/data \
    -e VITRANSCRIPT_ENABLE_TEST_MODEL=1 \
    -e VITRANSCRIPT_INSTANCE_TOKEN="e2e-sidecar-token-$(printf 'a%.0s' {1..32})" \
    "${IMAGE_TAG}" \
    bash -c '
      set -euo pipefail
      /sidecar --self-test-native
      # Full job/export via harness (harness is not part of product runtime).
      python3 /e2e.py --sidecar /sidecar --wav /sample.wav --data-home /data
    '
}

echo "==> clean runtime ONLINE (shared volume, network allowed)"
run_in_container

echo "==> clean runtime OFFLINE (--network none, same volume, no apt)"
run_in_container --network none

echo "E2E_CLEAN_UBUNTU PASS"
