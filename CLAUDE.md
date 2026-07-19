# ViTranscript — Context nhanh cho AI

## Dự án là gì

Ứng dụng **local-first** chạy Mac/Windows: chọn file audio/video → transcript tiếng Việt → xuất DOCX/XLSX/SRT/TXT. Không cloud, không API fee, chạy offline sau lần tải model đầu.

## Cấu trúc repo

```
docs/                   # Tài liệu kỹ thuật (KHÔNG chứa code)
  01-bai-toan.md        # Bài toán, quyết định kỹ thuật đã chốt, tiêu chí nghiệm thu
  02-plan.md            # Plan chi tiết từng task (code đầy đủ, interface, verify steps)
  03-tasks.md           # Bảng theo dõi trạng thái (xong/đang làm/chưa làm)
.worktrees/
  vitranscript-impl/    # Worktree thực thi — TOÀN BỘ CODE NẰM Ở ĐÂY
```

**Khi làm việc với code:** luôn `cd .worktrees/vitranscript-impl` hoặc dùng đường dẫn tuyệt đối vào worktree đó.

## Stack kỹ thuật

| Thành phần | Thư viện | Ghi chú |
|---|---|---|
| Transcript | faster-whisper (CTranslate2, CPU int8) | Không PyTorch |
| Diarization | sherpa-onnx (pyannote seg 3.0 ONNX + eres2net) | Không HF token |
| Web UI | FastAPI + 1 trang HTML tĩnh | localhost 127.0.0.1 |
| Cài đặt | `uv` (tự tải Python 3.12) | |
| Export | python-docx, openpyxl | |
| Sửa từ khóa | rapidfuzz (fuzzy) + hotwords faster-whisper | |

<!-- auto-update: start -->
## Trạng thái hiện tại

> _Phần này tự động cập nhật khi commit vào main._

**Tiến độ:** 17/20 task xong 🟢 | 2 đang chạy 🔵 | 1 chưa làm ⚪

**Module đã có trong `app/`:** `checkpoint.py`, `config.py`, `diarize.py`, `export.py`, `glossary.py`, `media.py`, `pipeline.py`, `segment.py`, `server.py`, `transcribe.py`

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
| 8 | Unit tests core (`tests/test_core.py`, 8 test) | 🟢 | 8 test pass |
| 9 | Web server FastAPI (`app/server.py`) | 🟢 | 409 nếu đã có job running; filename export = stem gốc |
| 10 | UI web tiếng Việt (`app/static/index.html`) | 🟢 | |
| 11 | Script cài đặt 1-click (4 file) | 🟢 | Windows cần máy thật để verify đầy đủ |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | 🟢 | **macOS:** smoke pass với model `tiny`; Windows → UI + unit tests |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | 🟢 | Scaffolding xong (`eval/README.md` + script). WER: — (chưa có sample người dùng) |
| 13 | README người dùng cuối | 🟢 | Đường dẫn data Mac/Windows/Linux; WER cột “chưa đo — cần eval/sample” |
| 14 | Nghiệm thu 6 tiêu chí + tag `v0.1.0` | 🔵 | Nghiệm thu một phần — chưa gắn tag `v0.1.0` (thiếu máy sạch / file dài / WER) |

**Rủi ro / việc treo đang mở:**
- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b: người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay để điền bảng WER
- [ ] GC thư mục jobs (disk) — v1: xóa thủ công qua README data path (không auto-delete)

**5 commit gần nhất:**

- `4b13de5 docs: thiet ke vo desktop v1.5 (script uv + app bundle + tray + uninstall sach)`
- `efded9e docs: plan review P0/P1 patches + worktrees gitignore`
- `c8c46cc docs: bai toan, plan, tasks — trang thai chua thuc thi`
<!-- auto-update: end -->


## Constraints quan trọng

- `requires-python = ">=3.10,<3.13"` — KHÔNG kéo PyTorch/TensorFlow
- Máy mục tiêu: macOS arm64, macOS x86_64, Windows x64 CPU-only
- v1: **1 job tại một thời điểm** — server 409 nếu có job đang chạy
- Server chỉ bind `127.0.0.1`
- Text UI: tiếng Việt; `.bat` viết không dấu (tránh lỗi codepage Windows)
- URL diarization: `"speaker-recongition-models"` — lỗi chính tả là CỐ Ý (upstream), không sửa

## Quy trình commit

Mỗi task: code → `uv run ruff check .` sạch → verify → `git commit`.
Commit message kết thúc bằng: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## Auto-update CLAUDE.md / AGENTS.md

Hai file này tự động cập nhật khi có commit vào `main` qua 2 lớp:
1. **Claude Code hook** (`.claude/settings.json`) — bắt `git commit` trong session
2. **Git hook** — cài một lần bằng: `bash scripts/install_hook.sh`

Chạy thủ công: `python3 scripts/update_context.py`

## Lệnh hay dùng (chạy từ `.worktrees/vitranscript-impl`)

```bash
uv sync                                  # cài dependencies
uv run ruff check .                      # lint
uv run pytest tests/ -v                  # unit tests (8 test)
uv run python -m app.server              # chạy app (mở browser tự động)
uv run python scripts/smoke_e2e.py       # smoke test macOS
uv run python scripts/eval_wer.py        # đo WER (cần eval/sample.*)
```

## Tham chiếu

- Bài toán + quyết định kỹ thuật đầy đủ: `docs/01-bai-toan.md`
- Plan chi tiết + code từng task: `docs/02-plan.md`
- Trạng thái tasks + WER + nghiệm thu: `docs/03-tasks.md`
