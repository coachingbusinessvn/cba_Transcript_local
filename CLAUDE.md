# ViTranscript — Context nhanh cho AI

## Dự án là gì

Ứng dụng **local-first** chạy Mac/Windows: chọn file audio/video → transcript tiếng Việt → xuất DOCX/XLSX/SRT/TXT. Không cloud, không API fee, chạy offline sau lần tải model đầu.

## Cấu trúc repo

```
docs/                   # Tài liệu kỹ thuật (KHÔNG chứa code)
  01-bai-toan.md        # Bài toán, quyết định kỹ thuật đã chốt, tiêu chí nghiệm thu
  02-plan.md            # Plan chi tiết từng task (code đầy đủ, interface, verify steps)
  03-tasks.md           # Bảng theo dõi trạng thái (xong/đang làm/chưa làm)
app/                    # Code ứng dụng (config, media, transcribe, diarize, pipeline, server…)
tests/                  # Unit test (test_core.py, test_punctuate.py)
scripts/                # smoke_e2e.py, eval_wer.py, eval_punctuation.py, smoke_punctuation_model.py
```

> Trước đây code nằm ở worktree `.worktrees/vitranscript-impl/`; từ bản merge 2026-07-24
> toàn bộ code đã gộp vào chính repo này. Vẫn có thể dùng worktree để phát triển tách biệt.

**Khi làm việc với code:** làm trực tiếp ở repo root (hoặc trong worktree phát triển nếu cần cô lập).

## Stack kỹ thuật

| Thành phần | Thư viện | Ghi chú |
|---|---|---|
| Transcript | faster-whisper (CTranslate2, CPU int8) | Không PyTorch |
| Diarization | sherpa-onnx (pyannote seg 3.0 ONNX + eres2net) | Không HF token |
| Web UI | FastAPI + 1 trang HTML tĩnh | localhost 127.0.0.1 |
| Cài đặt | `uv` (tự tải Python 3.12) | |
| Export | python-docx, openpyxl | |
| Sửa từ khóa | rapidfuzz (fuzzy) + hotwords faster-whisper | |
| Phục hồi dấu câu | ViBERT-CAPU ONNX (`app/punctuate.py`) | Tùy chọn, lazy load |

<!-- auto-update: start -->
## Trạng thái hiện tại

> _Phần này tự động cập nhật khi commit vào main._

**Tiến độ:** 17/21 task xong 🟢 | 3 đang chạy 🔵 | 1 chưa làm ⚪

**Module đã có trong `app/`:** _Worktree chưa có code._

**Bảng tasks (xem chi tiết: [docs/03-tasks.md](docs/03-tasks.md)):**

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
| 8 | Unit tests core (`tests/test_core.py` + `tests/test_punctuate.py`, 67 test) | 🟢 | 66 passed, 1 deselected |
| 9 | Web server FastAPI (`app/server.py`) | 🟢 | 409 nếu đã có job running; filename export = stem gốc |
| 10 | UI web tiếng Việt (`app/static/index.html`) | 🟢 | |
| 11 | Script cài đặt 1-click (4 file) | 🟢 | Windows cần máy thật để verify đầy đủ |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | 🟢 | **macOS:** smoke pass với model `tiny`; Windows → UI + unit tests |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | 🟢 | Scaffolding xong (`eval/README.md` + script). WER: — (chưa có sample người dùng) |
| 13 | README người dùng cuối | 🟢 | Đường dẫn data Mac/Windows/Linux; WER cột “chưa đo — cần eval/sample” |
| 14 | Nghiệm thu 6 tiêu chí + tag release | 🔵 | Beta: tag `v0.1.0-beta` (2026-07-24). GA `v0.1.0` chờ verify máy sạch / Windows / file dài / WER |
| 15 | Phục hồi dấu câu ViBERT-CAPU ONNX | 🔵 | Xem `docs/11-tasks-punctuation-restoration.md`; chưa nghiệm thu đủ PR-13/PR-14 |

**Rủi ro / việc treo đang mở:**
- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b: người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay để điền bảng WER
- [ ] GC thư mục jobs (disk) — v1: xóa thủ công qua README data path (không auto-delete)

**5 commit gần nhất:**

- `88b676e docs: them huong dan su dung day du macOS + Windows, sua port README 8765->8756`
- `cc44df9 docs: hook refresh danh sach commit gan nhat`
- `49cbfaa docs: release notes v0.1.0-beta + cap nhat nghiem thu Task 14`
- `5ae2b62 docs: refresh danh sach commit (hook) + sua so test 57 -> 66`
- `3b83f6d merge: dua toan bo code ViTranscript + 6 review-fix vao main`
<!-- auto-update: end -->


## Constraints quan trọng

- `requires-python = ">=3.10,<3.13"` — KHÔNG kéo PyTorch/TensorFlow
- Máy mục tiêu: macOS arm64, macOS x86_64, Windows x64 CPU-only
- v1: **1 job tại một thời điểm** — server 409 nếu có job đang chạy
- Server chỉ bind `127.0.0.1`
- Text UI: tiếng Việt; `.bat` viết không dấu (tránh lỗi codepage Windows)
- URL diarization: `"speaker-recongition-models"` — lỗi chính tả là CỐ Ý (upstream), không sửa

## RULE: Luôn cập nhật CLAUDE.md và AGENTS.md

**Bắt buộc cập nhật cả hai file mỗi khi có thay đổi sau:**

- Trạng thái task thay đổi (⚪ → 🔵 → 🟢)
- Thêm/xóa module, script, hoặc test file
- Thêm constraint hoặc quyết định kỹ thuật mới
- 5 commit gần nhất thay đổi (sau mỗi commit mới)
- Rủi ro/blocker mới xuất hiện hoặc được giải quyết

**Cách cập nhật:**
1. Sửa block `<!-- auto-update: start -->
## Trạng thái hiện tại

> _Phần này tự động cập nhật khi commit vào main._

**Tiến độ:** 17/21 task xong 🟢 | 3 đang chạy 🔵 | 1 chưa làm ⚪

**Module đã có trong `app/`:** _Worktree chưa có code._

**Bảng tasks (xem chi tiết: [docs/03-tasks.md](docs/03-tasks.md)):**

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
| 8 | Unit tests core (`tests/test_core.py` + `tests/test_punctuate.py`, 67 test) | 🟢 | 66 passed, 1 deselected |
| 9 | Web server FastAPI (`app/server.py`) | 🟢 | 409 nếu đã có job running; filename export = stem gốc |
| 10 | UI web tiếng Việt (`app/static/index.html`) | 🟢 | |
| 11 | Script cài đặt 1-click (4 file) | 🟢 | Windows cần máy thật để verify đầy đủ |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | 🟢 | **macOS:** smoke pass với model `tiny`; Windows → UI + unit tests |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | 🟢 | Scaffolding xong (`eval/README.md` + script). WER: — (chưa có sample người dùng) |
| 13 | README người dùng cuối | 🟢 | Đường dẫn data Mac/Windows/Linux; WER cột “chưa đo — cần eval/sample” |
| 14 | Nghiệm thu 6 tiêu chí + tag release | 🔵 | Beta: tag `v0.1.0-beta` (2026-07-24). GA `v0.1.0` chờ verify máy sạch / Windows / file dài / WER |
| 15 | Phục hồi dấu câu ViBERT-CAPU ONNX | 🔵 | Xem `docs/11-tasks-punctuation-restoration.md`; chưa nghiệm thu đủ PR-13/PR-14 |

**Rủi ro / việc treo đang mở:**
- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b: người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay để điền bảng WER
- [ ] GC thư mục jobs (disk) — v1: xóa thủ công qua README data path (không auto-delete)

**5 commit gần nhất:**

- `88b676e docs: them huong dan su dung day du macOS + Windows, sua port README 8765->8756`
- `cc44df9 docs: hook refresh danh sach commit gan nhat`
- `49cbfaa docs: release notes v0.1.0-beta + cap nhat nghiem thu Task 14`
- `5ae2b62 docs: refresh danh sach commit (hook) + sua so test 57 -> 66`
- `3b83f6d merge: dua toan bo code ViTranscript + 6 review-fix vao main`
<!-- auto-update: end -->` trong `CLAUDE.md`
2. Sửa block `<!-- status-block: start --> … <!-- status-block: end -->` trong `AGENTS.md`
3. Commit cả 2 file cùng với code thay đổi trong **cùng 1 commit**

> `CLAUDE.md` dùng cho Claude Code. `AGENTS.md` dùng cho AI khác (Codex, GPT, Gemini…). Nội dung trạng thái phải đồng bộ.

## Quy trình commit

Mỗi task: code → `uv run ruff check .` sạch → verify → cập nhật CLAUDE.md + AGENTS.md → `git commit`.
Commit message kết thúc bằng: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## Lệnh hay dùng (chạy từ repo root)

```bash
uv sync                                          # cài dependencies
uv run ruff check .                              # lint
uv run pytest tests/ -v                          # unit tests
uv run python -m app.server                      # chạy app (mở browser tự động)
uv run python scripts/smoke_e2e.py               # smoke test macOS
uv run python scripts/eval_wer.py                # đo WER (cần eval/sample.*)
uv run python scripts/smoke_punctuation_model.py # smoke test model dấu câu
uv run python scripts/eval_punctuation.py        # đánh giá chất lượng phục hồi dấu câu
```

## Tham chiếu

- Bài toán + quyết định kỹ thuật đầy đủ: `docs/01-bai-toan.md`
- Plan chi tiết + code từng task: `docs/02-plan.md`
- Trạng thái tasks + WER + nghiệm thu: `docs/03-tasks.md`
