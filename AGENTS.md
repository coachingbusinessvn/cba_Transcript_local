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
1. Edit the `<!-- auto-update: start --> … <!-- auto-update: end -->` block in `CLAUDE.md`
2. Edit the `<!-- status-block: start --> … <!-- status-block: end -->` block in `AGENTS.md`
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
| Localhost only | Server binds `127.0.0.1` only — never `0.0.0.0` |
| Intentional typo | `"speaker-recongition-models"` in diarization URL is an upstream typo — do NOT "fix" it |
| Windows `.bat` encoding | No Vietnamese diacritics in `.bat` scripts (Windows codepage issues) |
| `names` dict keys | Always strings: `"0"`, `"1"`, … — consistent across export / server / UI |

---

<!-- status-block: start -->
## Current status (2026-07-20)

**Progress:** 17/21 tasks done 🟢 | 2 in-progress 🔵 | 2 not started ⚪

**App modules in `.worktrees/vitranscript-impl/app/`:**
`checkpoint.py`, `config.py`, `diarize.py`, `export.py`, `glossary.py`, `media.py`, `pipeline.py`, `punctuate.py`, `segment.py`, `server.py`, `transcribe.py`

**Task table:**

| # | Task | Status | Notes |
|---|------|--------|-------|
| 0 | Project scaffold (`pyproject.toml` + ruff, `.python-version`, package `app`) | 🟢 | `uv.lock` committed; `numpy>=1.26` explicit |
| 1 | Config & model registry (`app/config.py`) | 🟢 | HF repos verified 2026-07-17 |
| 2 | Media / ffmpeg (`app/media.py`) | 🟢 | |
| 3 | Transcribe faster-whisper (`app/transcribe.py`) | 🟢 | hotwords + fallback; 1 model cached per process |
| 4 | Diarization sherpa-onnx (`app/diarize.py`) | 🟢 | |
| 5 | Glossary 2-tier (`app/glossary.py`) | 🟢 | |
| 6 | Sentence split + speaker assign (`app/segment.py`) | 🟢 | |
| 7 | Export DOCX/XLSX/SRT/TXT (`app/export.py`) | 🟢 | DOCX table style with try/except |
| 7b | Master pipeline (`app/pipeline.py`) | 🟢 | Uses cached `load_model` |
| 8 | Unit tests core (`tests/test_core.py`, 8 tests) | 🟢 | 8 tests pass |
| 9 | FastAPI web server (`app/server.py`) | 🟢 | HTTP 409 on duplicate job; export filename = source stem |
| 10 | Vietnamese web UI (`app/static/index.html`) | 🟢 | |
| 11 | 1-click install scripts (4 files) | 🟢 | Windows needs real machine to verify fully |
| 12 | E2E smoke test (`scripts/smoke_e2e.py`) | 🟢 | macOS: pass with `tiny` model; Windows → UI + unit tests |
| 12b | WER golden file (`scripts/eval_wer.py`) | 🟢 | Scaffolding done; WER = — (no user audio sample yet) |
| 13 | End-user README | 🟢 | Data paths Mac/Windows/Linux; WER column "not yet measured" |
| 14 | Acceptance test 6 criteria + tag `v0.1.0` | 🔵 | Partial pass — no tag yet (missing clean machine / long file / WER) |
| 15 | Punctuation restoration ViBERT-CAPU ONNX (`app/punctuate.py`) | 🔵 | Module + UI + tests done; release gates PR-13/PR-14 not fully verified |

**Open risks / blockers:**
- [ ] Windows installer verify — no real Windows machine available
- [ ] Diarization quality on shared-mic recordings — needs real user audio
- [ ] Task 12b: user must supply 3–5 min real audio + manual transcript for WER
- [ ] Task 15: punctuation release gates PR-13/PR-14 not fully verified
- [ ] Job output GC (disk) — v1: manual deletion via README data path

**5 most recent commits (worktree):**
- `7660b72 docs: verify punctuation restoration release gates`
- `2594ed3 test: align UI contract with punctuationMeta helper`
- `4f1ca45 feat: add punctuation UI option`
- `205103e feat: expose punctuation job option`
- `9022e6c feat: add punctuation pipeline stage`
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

Flow per task: code → `uv run ruff check .` clean → verify step → commit.

Trailer required on every commit:
```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```
