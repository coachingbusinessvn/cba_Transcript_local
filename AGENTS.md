# ViTranscript — Agent Context

> Canonical context file for AI agents (Codex, Gemini, GPT, etc.).
> Human-readable counterpart: `CLAUDE.md` (Claude Code specific).
> Detail docs: `docs/01-bai-toan.md`, `docs/02-plan.md`, `docs/03-tasks.md`.

---

## MANDATORY UPDATE RULE

**Every AI agent MUST update both `CLAUDE.md` and `AGENTS.md` whenever any of the following change:**

- A task status changes (⚪ → 🔵 → 🟢)
- A new module, script, or test file is added or removed
- A new constraint or architectural decision is made
- The 5 most recent commits change
- A new risk or blocker is identified or resolved

**How to update:**
1. Edit the auto-update block (between `auto-update` HTML comments) in `CLAUDE.md`
2. Edit the status block (between `status-block` HTML comments) in `AGENTS.md`
3. Keep both files in sync — they describe the same project state
4. Commit the updated context files together with the code change in the same commit

**Do not skip this step.** Stale context files cause future agents to work from wrong assumptions.

---

## What this project is

Local-first Vietnamese transcription desktop app (Mac/Windows).

- **Input:** audio or video file
- **Output:** DOCX / XLSX / SRT / TXT with timestamps and speaker labels
- **Key property:** fully offline after first model download — no cloud, no API fees

---

## Repository layout

```
CLAUDE.md                   Claude Code context (auto-updated)
AGENTS.md                   This file — context for all other AI agents (auto-updated)
docs/
  01-bai-toan.md            Problem statement, tech decisions, acceptance criteria
  02-plan.md                Per-task plan with full code, interfaces, verify steps
  03-tasks.md               Task tracking table (done / in-progress / todo, WER results)
  11-tasks-punctuation-restoration.md   Punctuation task spec
.worktrees/
  vitranscript-impl/        ALL CODE lives here (git worktree, branch: vitranscript-impl)
```

**Working directory rule:** always use `.worktrees/vitranscript-impl/` when reading or editing code.

---

## Tech stack

| Component | Library | Constraint |
|---|---|---|
| Transcript | faster-whisper (CTranslate2, CPU int8) | NO PyTorch |
| Diarization | sherpa-onnx (pyannote seg3 ONNX + eres2net) | No HF token needed |
| Punctuation restoration | ViBERT-CAPU ONNX (`app/punctuate.py`) | Optional, lazy-loaded |
| Keyword correction | rapidfuzz (fuzzy) + hotwords faster-whisper | |
| Web UI | FastAPI + single static HTML | localhost 127.0.0.1 only |
| Install | `uv` (self-installs Python 3.12) | |
| Export | python-docx, openpyxl | |
| Python | `>=3.10,<3.13` | |
| Target OS | macOS arm64, macOS x86_64, Windows x64 | CPU-only |

---

## Hard constraints — never violate

| Constraint | Detail |
|---|---|
| No heavy ML frameworks | NO dependency that pulls PyTorch or TensorFlow |
| Single job | v1: one job at a time — server returns HTTP 409 if a job is running |
| Localhost only | Server binds `127.0.0.1` only — never `0.0.0.0`. Middleware `_security_guard`: Host must be loopback (anti-DNS-rebinding), write requests with cross-site Origin/`Sec-Fetch-Site` get 403 (anti-CSRF); `job_id` must be uuid-hex-12 (anti-path-traversal) |
| onnxruntime `<1.24` | 1.23.x is the last release with macOS x86_64 wheels (1.24 has no macOS wheel, 1.25+ is arm64-only) — bumping breaks install on Intel Macs |
| Intentional typo | `"speaker-recongition-models"` in diarization URL is an upstream typo — do NOT "fix" it |
| Windows `.bat` encoding | No Vietnamese diacritics in `.bat` scripts (Windows codepage issues) |
| `names` dict keys | Always strings: `"0"`, `"1"`, … — consistent across export / server / UI |

---

<!-- status-block: start -->
## Current status

**Progress:** 17/21 tasks done 🟢 | 3 in-progress 🔵 | 1 not started ⚪

**App modules in `app/`:**
`checkpoint.py`, `config.py`, `diarize.py`, `export.py`, `glossary.py`, `janitor.py`, `media.py`, `pipeline.py`, `punctuate.py`, `segment.py`, `server.py`, `transcribe.py`

**Task table:**

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
| 8 | Unit tests core (`tests/test_core.py` + `tests/test_punctuate.py` + `tests/test_janitor.py`, 83 test) | 🟢 | 82 passed, 1 deselected |
| 9 | Web server FastAPI (`app/server.py`) | 🟢 | 409 nếu đã có job running; security middleware: Host loopback-only (chống DNS rebinding), chặn POST cross-site (chống CSRF), `job_id` whitelist hex-12, upload ≤ 8 GB |
| 10 | UI web tiếng Việt (`app/static/index.html`) | 🟢 | |
| 11 | Script cài đặt 1-click (4 file) | 🟢 | Windows cần máy thật để verify đầy đủ |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | 🟢 | **macOS:** smoke pass với model `tiny`; Windows → UI + unit tests |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | 🟢 | Scaffolding xong (`eval/README.md` + script). WER: — (chưa có sample người dùng) |
| 13 | README người dùng cuối | 🟢 | Đường dẫn data Mac/Windows/Linux; WER cột “chưa đo — cần eval/sample” |
| 14 | Nghiệm thu 6 tiêu chí + tag release | 🔵 | Beta: tag `v0.1.0-beta` (2026-07-24). GA `v0.1.0` chờ verify máy sạch / Windows / file dài / WER |
| 15 | Phục hồi dấu câu ViBERT-CAPU ONNX | 🔵 | Xem `docs/11-tasks-punctuation-restoration.md`; chưa nghiệm thu đủ PR-13/PR-14 |

**Open risks / blockers:**
- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b: người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay để điền bảng WER
- [x] GC thư mục jobs (disk) — auto-GC `app/janitor.py` chạy 1 lần lúc server khởi động: xóa job >30 ngày; jobs/ >20 GB thì xóa cũ nhất trước, luôn giữ 10 job mới nhất; không đụng job `running`
<!-- status-block: end -->

---

## Module reference

| Module | Key exports | Purpose |
|---|---|---|
| `config.py` | `MODEL_REGISTRY`, `data_dir()`, `load_settings()`, `load_glossary_text()` | Paths, model configs, user settings |
| `media.py` | `extract_audio()`, `to_wav16k()`, `read_wav16k_float32()` | ffmpeg wrappers |
| `transcribe.py` | `load_model(key)` [cached], `transcribe()` → `list[Word]` | faster-whisper |
| `diarize.py` | `ensure_models()`, `diarize()` → `list[SpeakerTurn]` | sherpa-onnx |
| `punctuate.py` | `load_punctuation_model()` [lazy], `restore_punctuation()` | ViBERT-CAPU ONNX |
| `glossary.py` | `parse()`, `correct()` | Exact + fuzzy keyword correction |
| `segment.py` | `build_sentences()`, `assign_speakers()` | Sentence split + speaker label |
| `export.py` | `to_docx/xlsx/srt/txt()`, `speaker_name()` | Output formats |
| `pipeline.py` | `run()` | Master pipeline, progress callback |
| `checkpoint.py` | save/restore partial results | Long-file resilience |
| `janitor.py` | `cleanup_jobs_dir()` | Auto-GC `jobs/` at startup (>30d old, >20 GB cap, keep 10 newest, never `running`) |
| `server.py` | FastAPI app | REST API + static file serving |

---

## Runtime data directory

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/ViTranscript/` |
| Windows | `%APPDATA%\ViTranscript\` |

Contents: `models/` (HF cache), `jobs/` (output), `settings.json`, `glossary.txt`, `diarization/` (~30 MB ONNX models)

---

## Dev commands (from `.worktrees/vitranscript-impl/`)

```bash
uv sync                                          # install / update deps
uv run ruff check .                              # lint — must be clean before commit
uv run pytest tests/ -v                          # unit tests
uv run python -m app.server                      # run app (auto-opens browser, port 8756+)
uv run python scripts/smoke_e2e.py               # macOS smoke test
uv run python scripts/eval_wer.py                # WER (needs eval/sample.*)
uv run python scripts/smoke_punctuation_model.py # smoke test punctuation model
uv run python scripts/eval_punctuation.py        # punctuation quality eval
```

---

## Commit convention

Flow per task: code → `uv run ruff check .` clean → verify step → update CLAUDE.md + AGENTS.md → commit.

Trailer required on every commit:
```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```
