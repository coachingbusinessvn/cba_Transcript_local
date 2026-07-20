# ViTranscript — Worktree thực thi

> Đây là worktree code chính. Tài liệu đầy đủ ở repo gốc: `docs/01-bai-toan.md`, `docs/02-plan.md`, `docs/03-tasks.md`.

## Dự án

Ứng dụng local-first transcript tiếng Việt: file audio/video → văn bản có timestamp + người nói → DOCX/XLSX/SRT/TXT. Chạy offline trên Mac/Windows, không cloud, không API fee.

## Cấu trúc code

```
app/
  config.py       MODEL_REGISTRY, data_dir(), load_settings(), load_glossary_text()
  media.py        ffmpeg: extract_audio, to_wav16k, read_wav16k_float32
  transcribe.py   load_model(key) [cached], transcribe() → list[Word]
  diarize.py      ensure_models(), diarize() → list[SpeakerTurn]
  glossary.py     parse(), correct() — exact replace + fuzzy snap (rapidfuzz)
  segment.py      build_sentences(), assign_speakers()
  export.py       to_docx/xlsx/srt/txt, speaker_name()
  pipeline.py     run() — ghép toàn bộ flow, progress callback
  checkpoint.py   lưu/khôi phục partial để hỗ trợ file dài
  server.py       FastAPI: GET /api/meta, POST /api/jobs, GET /api/jobs/{id}, POST export
  static/
    index.html    UI tiếng Việt (thuần HTML/CSS/JS, offline)
tests/
  test_core.py, test_punctuate.py    57 unit tests (1 deselected)
scripts/
  smoke_e2e.py    smoke test macOS (dùng lệnh `say`)
  eval_wer.py     đo WER với golden file trong eval/
```

## Stack

- **Transcript:** faster-whisper (CTranslate2, CPU int8) — không PyTorch
- **Diarization:** sherpa-onnx (pyannote segmentation 3.0 ONNX + eres2net embedding)
- **Web:** FastAPI + uvicorn, 1 trang HTML tĩnh, localhost 127.0.0.1
- **Cài đặt:** `uv` (tự tải Python 3.12)
- **Python:** `>=3.10,<3.13`

## Constraints không được vi phạm

- KHÔNG thêm dependency kéo PyTorch/TensorFlow
- v1: **1 job tại một thời điểm** — server trả HTTP 409 nếu đang có job running
- Server chỉ bind `127.0.0.1` — không bind `0.0.0.0`
- URL diarization chứa `"speaker-recongition-models"` — lỗi chính tả là CỐ Ý (upstream repo), không được "sửa"
- Text UI: tiếng Việt; `.bat` viết không dấu (tránh lỗi codepage Windows)
- `names` dict dùng key kiểu chuỗi: `"0"`, `"1"`,... (nhất quán qua export/server/UI)

## Lệnh nhanh

```bash
uv sync                           # cài/cập nhật dependencies
uv run ruff check .               # lint (phải sạch trước commit)
uv run pytest tests/ -v           # unit tests — expected: 57 passed, 1 deselected
uv run python -m app.server       # chạy app (tự mở browser port 8756+)
uv run python scripts/smoke_e2e.py    # smoke test macOS
uv run python scripts/eval_wer.py     # đo WER (cần eval/sample.*)
```

## Data directory (runtime)

- macOS: `~/Library/Application Support/ViTranscript/`
- Windows: `%APPDATA%\ViTranscript\`
- Gồm: `models/` (cache HF), `jobs/` (job output), `settings.json`, `glossary.txt`, `diarization/` (ONNX models ~30MB)

## Model registry

| Key | Source HF | Size |
|---|---|---|
| `phowhisper-small` | diepho/PhoWhisper-small-ct2 | ~490MB (mặc định) |
| `phowhisper-medium` | diepho/PhoWhisper-medium-ct2 | ~1.5GB |
| `phowhisper-large` | kiendt/PhoWhisper-large-ct2 | ~3GB |
| `large-v3-turbo` | deepdml/faster-whisper-large-v3-turbo-ct2 | ~1.6GB |
| `whisper-small` | small (built-in) | ~490MB |

## Quy trình commit

Mỗi thay đổi: code → `uv run ruff check .` → verify → commit.
Commit message kết thúc: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
