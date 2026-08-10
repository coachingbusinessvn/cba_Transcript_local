#!/usr/bin/env bash
# Headless Tauri smoke under Xvfb: window appears, close exits, sidecar port closes.
# Usage: scripts/smoke_desktop_linux.sh <path-to-AppImage-or-release-bin>
set -euo pipefail

BIN="${1:-}"
if [[ -z "${BIN}" || ! -e "${BIN}" ]]; then
  echo "Usage: $0 <release-or-appimage-path>" >&2
  exit 1
fi

if ! command -v xvfb-run >/dev/null 2>&1; then
  echo "ERROR: xvfb-run required (apt install xvfb)" >&2
  exit 1
fi
if ! command -v xdotool >/dev/null 2>&1; then
  echo "ERROR: xdotool required (apt install xdotool)" >&2
  exit 1
fi

WORKDIR="$(mktemp -d /tmp/vitranscript-smoke-XXXXXX)"
export XDG_DATA_HOME="${WORKDIR}/data"
export XDG_CONFIG_HOME="${WORKDIR}/config"
export XDG_CACHE_HOME="${WORKDIR}/cache"
mkdir -p "${XDG_DATA_HOME}" "${XDG_CONFIG_HOME}" "${XDG_CACHE_HOME}"

LOG="${WORKDIR}/app.log"
READY_LOG="${WORKDIR}/ready.txt"

cleanup() {
  if [[ -n "${APP_PID:-}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
    kill "${APP_PID}" 2>/dev/null || true
    sleep 1
    kill -9 "${APP_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> launch under xvfb: ${BIN}"
# AppImage may need extract mode without FUSE
RUN=("${BIN}")
if [[ "${BIN}" == *.AppImage ]]; then
  chmod +x "${BIN}" || true
  RUN=("${BIN}" --appimage-extract-and-run)
fi

# Mirror READY from Tauri stdout
(
  xvfb-run -a -s "-screen 0 1280x800x24" "${RUN[@]}" >"${LOG}" 2>&1
) &
APP_PID=$!

# Wait window
echo "==> wait window ViTranscript (60s)"
FOUND=0
for _ in $(seq 1 60); do
  if xdotool search --name '^ViTranscript$' >/dev/null 2>&1; then
    FOUND=1
    break
  fi
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    echo "app exited early"; tail -50 "${LOG}" || true
    exit 1
  fi
  sleep 1
done
if [[ "${FOUND}" -ne 1 ]]; then
  echo "ERROR: window not found"; tail -80 "${LOG}" || true
  exit 1
fi
WIDS="$(xdotool search --name '^ViTranscript$' || true)"
COUNT="$(echo "${WIDS}" | grep -c . || true)"
echo "windows: ${COUNT}"
if [[ "${COUNT}" -lt 1 ]]; then
  echo "ERROR: expected >=1 window"
  exit 1
fi

# Extract READY port from log if mirrored
PORT="$(grep -E 'VITRANSCRIPT_READY http://127\.0\.0\.1:' "${LOG}" | head -1 | sed -E 's/.*:([0-9]+)$/\1/' || true)"
echo "READY port from log: ${PORT:-none}"

echo "==> close window"
WID="$(echo "${WIDS}" | head -1)"
xdotool windowactivate "${WID}" || true
xdotool windowclose "${WID}" || true

echo "==> wait app exit (15s)"
for _ in $(seq 1 15); do
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    echo "app exited"
    break
  fi
  sleep 1
done
if kill -0 "${APP_PID}" 2>/dev/null; then
  echo "ERROR: app still running after close"
  exit 1
fi

if [[ -n "${PORT}" ]]; then
  if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
    echo "ERROR: port ${PORT} still listening"
    exit 1
  fi
  echo "port ${PORT} closed"
fi

echo "SMOKE_DESKTOP PASS"
