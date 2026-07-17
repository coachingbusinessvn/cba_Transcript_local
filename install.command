#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== Cài đặt ViTranscript ==="
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "Đang cài công cụ uv (tự quản lý Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv sync
echo
echo "✅ Cài đặt hoàn tất! Mở ứng dụng bằng cách nhấp đúp file run.command"
read -n 1 -s -r -p "Nhấn phím bất kỳ để đóng…"
