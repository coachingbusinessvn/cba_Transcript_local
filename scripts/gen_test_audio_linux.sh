#!/usr/bin/env bash
# Generate Vietnamese speech WAV for e2e (espeak-ng + ffmpeg).
# Usage: scripts/gen_test_audio_linux.sh [out.wav]
set -euo pipefail

OUT="${1:-/tmp/vitranscript-e2e-sample.wav}"
TMP_RAW="$(mktemp /tmp/vitranscript-espeak-XXXXXX.wav)"

cleanup() { rm -f "${TMP_RAW}"; }
trap cleanup EXIT

if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "ERROR: espeak-ng not found. Install: sudo apt-get install -y espeak-ng" >&2
  exit 1
fi

# Prefer bundled ffmpeg from media if available; else system.
FFMPEG="${VITRANSCRIPT_BUNDLE_FFMPEG:-}"
if [[ -z "${FFMPEG}" || ! -x "${FFMPEG}" ]]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    FFMPEG="$(command -v ffmpeg)"
  else
    echo "ERROR: ffmpeg not found" >&2
    exit 1
  fi
fi

TEXT="Xin chào. Đây là bài kiểm tra ViTranscript trên Ubuntu. \
Chúng tôi đang chuyển giọng nói tiếng Việt thành văn bản. \
Một hai ba bốn năm. Cảm ơn bạn đã lắng nghe."

echo "==> espeak-ng -v vi"
espeak-ng -v vi -s 140 -w "${TMP_RAW}" "${TEXT}"

echo "==> ffmpeg normalize 16k mono -> ${OUT}"
"${FFMPEG}" -hide_banner -y -i "${TMP_RAW}" -ac 1 -ar 16000 -c:a pcm_s16le "${OUT}"

# Duration check via ffprobe if available
if command -v ffprobe >/dev/null 2>&1; then
  DUR="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${OUT}" || echo 0)"
  python3 - <<PY
d=float("${DUR}" or 0)
print(f"duration={d:.2f}s")
if d <= 5.0:
    raise SystemExit(f"ERROR: duration {d}s <= 5s")
PY
fi

echo "OK wrote ${OUT}"
