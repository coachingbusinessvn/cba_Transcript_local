#!/usr/bin/env bash
# Headless Tauri smoke under Xvfb: window appears, close exits, sidecar port closes.
# Usage: scripts/smoke_desktop_linux.sh <path-to-AppImage-or-release-bin>
#
# App and xdotool MUST share the same DISPLAY. xvfb-run only exports DISPLAY to its
# child, so parent-shell xdotool would miss the window. We start Xvfb ourselves.
set -euo pipefail

BIN="${1:-}"
if [[ -z "${BIN}" || ! -e "${BIN}" ]]; then
  echo "Usage: $0 <release-or-appimage-path>" >&2
  exit 1
fi

if ! command -v Xvfb >/dev/null 2>&1; then
  echo "ERROR: Xvfb required (apt install xvfb)" >&2
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
XVFB_PID=""
APP_PID=""

cleanup() {
  if [[ -n "${APP_PID:-}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
    kill "${APP_PID}" 2>/dev/null || true
    sleep 1
    kill -9 "${APP_PID}" 2>/dev/null || true
  fi
  if [[ -n "${XVFB_PID:-}" ]] && kill -0 "${XVFB_PID}" 2>/dev/null; then
    kill "${XVFB_PID}" 2>/dev/null || true
    wait "${XVFB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Pick a free display number
DISPLAY_NUM=""
for n in $(seq 99 119); do
  if [[ ! -e "/tmp/.X${n}-lock" ]]; then
    DISPLAY_NUM="${n}"
    break
  fi
done
if [[ -z "${DISPLAY_NUM}" ]]; then
  echo "ERROR: no free X display in :99–:119" >&2
  exit 1
fi

echo "==> start Xvfb :${DISPLAY_NUM}"
Xvfb ":${DISPLAY_NUM}" -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
XVFB_PID=$!
export DISPLAY=":${DISPLAY_NUM}"
# Brief settle so clients can connect
for _ in $(seq 1 20); do
  if kill -0 "${XVFB_PID}" 2>/dev/null; then
    break
  fi
  sleep 0.1
done
if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
  echo "ERROR: Xvfb failed to start" >&2
  exit 1
fi
sleep 0.3

echo "==> launch under DISPLAY=${DISPLAY}: ${BIN}"
# AppImage may need extract mode without FUSE
RUN=("${BIN}")
if [[ "${BIN}" == *.AppImage ]]; then
  chmod +x "${BIN}" || true
  RUN=("${BIN}" --appimage-extract-and-run)
fi

"${RUN[@]}" >"${LOG}" 2>&1 &
APP_PID=$!

# Wait window (xdotool on same DISPLAY as app)
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
APP_PID=""

if [[ -n "${PORT}" ]]; then
  if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
    echo "ERROR: port ${PORT} still listening"
    exit 1
  fi
  echo "port ${PORT} closed"
fi

echo "SMOKE_DESKTOP PASS"
