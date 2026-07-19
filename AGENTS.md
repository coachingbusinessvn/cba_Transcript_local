# ViTranscript — Agent Context

> Auto-generated. Do not edit manually — regenerated on every commit to main.
> Canonical detail docs: `docs/01-bai-toan.md`, `docs/02-plan.md`, `docs/03-tasks.md`.

## What this project is

Local-first Vietnamese transcription app (Mac/Windows). Input: audio/video file.
Output: DOCX/XLSX/SRT/TXT with timestamps and speaker labels. Fully offline after first model download.

## Repository layout

```
docs/              Technical docs (no code here)
  01-bai-toan.md   Problem statement, tech decisions, acceptance criteria
  02-plan.md       Per-task plan with full code, interfaces, verify steps
  03-tasks.md      Task tracking table (status, notes, WER results)
.worktrees/
  vitranscript-impl/   ALL CODE lives here (git worktree branch)
CLAUDE.md          AI-context file (auto-updated)
AGENTS.md          This file (auto-updated)
```

**Important:** to work with code, always use `.worktrees/vitranscript-impl/` path.

## Tech stack

| Component | Library | Constraint |
|---|---|---|
| Transcript | faster-whisper (CTranslate2, CPU int8) | NO PyTorch |
| Diarization | sherpa-onnx (pyannote seg3 ONNX + eres2net) | No HF token needed |
| Web UI | FastAPI + single static HTML | localhost 127.0.0.1 only |
| Install | `uv` (self-installs Python 3.12) | |
| Python | `>=3.10,<3.13` | |

## Current implementation status (17/20 tasks done)

| # | Task | Trạng thái | Ghi chú |
|---|------|-----------|---------|
| 0 | Khung dự án (`pyproject.toml` + ruff, `.python-version`, package `app`) | 🟢 | Commit `uv.lock`; có `numpy>=1.26` |
| 1 | Config & model registry (`app/config.py`) | 🟢 | Model repos đã verify tồn tại trên HF (2026-07-17) |
| 2 | Media/ffmpeg (`app/media.py`) | 🟢 | |
| 3 | Transcribe faster-whisper (`app/transcribe.py`) | 🟢 | `hotwords` + fallback; cache 1 model/process |
| 4 | Diarization sherpa-onnx (`app/diarize.py`) | 🟢 | |
| 5 | Glossary 2 tầng (`app/glossary.py`) | 🟢 | |
| 6 | Tách câu + gán speaker (`app/segment.py`) | 🟢 | |
| 7 | Export DOCX/XLSX/SRT/TXT (`app/export.py`) | 🟢 | DOCX table style try/except |
| 7b | Pipeline tổng (`app/pipeline.py`) | 🟢 | Dùng `load_model` đã cache |
| 8 | Unit tests core (`tests/test_core.py`, 8 test) | 🟢 | 8 test pass |
| 9 | Web server FastAPI (`app/server.py`) | 🟢 | 409 nếu đã có job running; filename export = stem gốc |
| 10 | UI web tiếng Việt (`app/static/index.html`) | 🟢 | |
| 11 | Script cài đặt 1-click (4 file) | 🟢 | Windows cần máy thật để verify đầy đủ |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | 🟢 | **macOS:** smoke pass với model `tiny`; Windows → UI + unit tests |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | 🟢 | Scaffolding xong (`eval/README.md` + script). WER: — (chưa có sample người dùng) |
| 13 | README người dùng cuối | 🟢 | Đường dẫn data Mac/Windows/Linux; WER cột “chưa đo — cần eval/sample” |
| 14 | Nghiệm thu 6 tiêu chí + tag `v0.1.0` | 🔵 | Nghiệm thu một phần — chưa gắn tag `v0.1.0` (thiếu máy sạch / file dài / WER) |

**App modules present:** `checkpoint.py`, `config.py`, `diarize.py`, `export.py`, `glossary.py`, `media.py`, `pipeline.py`, `segment.py`, `server.py`, `transcribe.py`

**Recent commits:**

- `4b13de5 docs: thiet ke vo desktop v1.5 (script uv + app bundle + tray + uninstall sach)`
- `efded9e docs: plan review P0/P1 patches + worktrees gitignore`
- `c8c46cc docs: bai toan, plan, tasks — trang thai chua thuc thi`

## Hard constraints (never violate)

- NO dependency that pulls PyTorch or TensorFlow
- v1: **one job at a time** — server returns HTTP 409 if a job is already running
- Server binds `127.0.0.1` only — never `0.0.0.0`
- `"speaker-recongition-models"` in diarization URL — intentional typo from upstream, do NOT "fix"
- `.bat` scripts: no Vietnamese diacritics (Windows codepage issues)
- `names` dict keys are always strings: `"0"`, `"1"`, ... (consistent across export/server/UI)

## Dev commands (run from `.worktrees/vitranscript-impl/`)

```bash
uv sync                           # install/update deps
uv run ruff check .               # lint (must be clean before commit)
uv run pytest tests/ -v           # 8 unit tests
uv run python -m app.server       # start app (auto-opens browser at port 8756+)
uv run python scripts/smoke_e2e.py    # macOS smoke test
uv run python scripts/eval_wer.py     # WER measurement (needs eval/sample.*)
```

## Commit convention

Each task: code → `uv run ruff check .` → verify → commit.
Trailer line: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
