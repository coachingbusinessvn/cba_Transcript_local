# Tasks — ViTranscript

> Bảng theo dõi thực thi. Chi tiết từng task (file, interface, code đầy đủ, lệnh verify) xem [02-plan.md](02-plan.md). Bài toán gốc xem [01-bai-toan.md](01-bai-toan.md).
>
> **Quy trình mỗi task:** code → `uv run ruff check .` sạch → chạy verify của task → commit. Xem Global Constraints trong plan.
>
> **Plan review (2026-07-17):** đã vá P0/P1 vào `02-plan.md` (numpy, model cache, single-job 409, DOCX style an toàn, checklist QA UI, smoke macOS-only, đường dẫn data README).
>
> **Cập nhật (2026-07-17):** Tasks 0–12, 12b (scaffolding), 13 đã xong. Smoke E2E đã pass trên macOS với model `tiny`. Task 12b chưa có số WER (thiếu `eval/sample.*` từ người dùng). Task 14 chưa làm.

**Trạng thái:** 🟢 xong (đã verify + commit) · 🔵 đang làm · ⚪ chưa làm

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

## Kết quả đo WER (Task 12b — điền khi chạy)

| Model | WER | Thời gian xử lý | Ghi chú |
|---|---|---|---|
| phowhisper-small | — | — | Cần `eval/sample.*` + `eval/sample.txt` |
| large-v3-turbo | — | — | Cần `eval/sample.*` + `eval/sample.txt` |

## Kết quả nghiệm thu (Task 14 — điền khi chạy)

| Tiêu chí | Kết quả | Ghi chú |
|---|---|---|
| 1. Cài trên máy sạch không lỗi | PARTIAL | Script `install.command`/`install.bat` có sẵn; `uv sync` pass trên máy dev — chưa thử máy sạch / Windows |
| 2. `run` tự mở browser + UI tiếng Việt | PASS (dev) | `TestClient` GET `/` + `/api/meta` OK; `main()` mở browser sau 1.5s |
| 3. File dài → DOCX/XLSX đủ timestamp, người nói, câu | PARTIAL | Smoke E2E (audio ngắn `say` + tiny) tạo DOCX/XLSX; chưa thử file ~30 phút |
| 4. Glossary sửa đúng từ khai báo | PASS | Unit tests exact + fuzzy (`NVIDIA`, `Vinamilk`) |
| 5. Chạy offline sau lần tải model đầu | — | Chưa tắt mạng thử có hệ thống |
| 6. WER trên audio mẫu thật ≤ 30% | BLOCKED | Chờ người dùng cung cấp `eval/sample.*` + `sample.txt` |

## Việc treo / rủi ro đang mở

- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b: người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay để điền bảng WER
- [ ] GC thư mục jobs (disk) — v1: xóa thủ công qua README data path (không auto-delete)
- [x] ~~Job song song OOM~~ — đã chốt: 1 job + HTTP 409 (plan review)
- [x] ~~Reload model mỗi job~~ — đã chốt: cache 1 model/process (plan review)
- [x] ~~numpy transitive only~~ — đã khai báo tường minh (plan review)
- [x] ~~Smoke E2E macOS~~ — pass với model tiny
