# Tasks — ViTranscript

> Bảng theo dõi thực thi. Chi tiết từng task (file, interface, code đầy đủ, lệnh verify) xem [02-plan.md](02-plan.md). Bài toán gốc xem [01-bai-toan.md](01-bai-toan.md).
>
> **Trạng thái repo:** chỉ có tài liệu — CHƯA có dòng code nào được thực thi. Code nháp viết trước khi chốt plan đã được gỡ bỏ và chuyển toàn bộ vào 02-plan.md (2026-07-17).
>
> **Quy trình mỗi task:** code → `uv run ruff check .` sạch → chạy verify của task → commit. Xem Global Constraints trong plan.

**Trạng thái:** 🟢 xong (đã verify + commit) · 🔵 đang làm · ⚪ chưa làm

| # | Task | Trạng thái | Ghi chú |
|---|------|-----------|---------|
| 0 | Khung dự án (`pyproject.toml` + ruff, `.python-version`, package `app`) | ⚪ | Commit `uv.lock` ngay sau `uv sync` đầu tiên |
| 1 | Config & model registry (`app/config.py`) | ⚪ | Model repos đã verify tồn tại trên HF (2026-07-17) |
| 2 | Media/ffmpeg (`app/media.py`) | ⚪ | |
| 3 | Transcribe faster-whisper (`app/transcribe.py`) | ⚪ | `hotwords` cần faster-whisper ≥1.0.2; fallback ghi trong plan |
| 4 | Diarization sherpa-onnx (`app/diarize.py`) | ⚪ | URL model đã verify HTTP 200 (2026-07-17) |
| 5 | Glossary 2 tầng (`app/glossary.py`) | ⚪ | |
| 6 | Tách câu + gán speaker (`app/segment.py`) | ⚪ | |
| 7 | Export DOCX/XLSX/SRT/TXT (`app/export.py`) | ⚪ | |
| 7b | Pipeline tổng (`app/pipeline.py`) | ⚪ | |
| 8 | Unit tests core (`tests/test_core.py`, 8 test) | ⚪ | Lần verify logic đầu tiên của Task 1, 5, 6, 7 |
| 9 | Web server FastAPI (`app/server.py`) | ⚪ | Code đầy đủ trong plan |
| 10 | UI web tiếng Việt (`app/static/index.html`) | ⚪ | Spec 6 mục trong plan |
| 11 | Script cài đặt 1-click (4 file) | ⚪ | Windows cần máy thật để verify |
| 12 | Smoke test E2E (`scripts/smoke_e2e.py`) + sửa lỗi | ⚪ | Chốt chặn lệch API sherpa-onnx / faster-whisper |
| 12b | Golden file — đo WER (`scripts/eval_wer.py`) | ⚪ | Cần người dùng cung cấp audio thật + transcript tay |
| 13 | README người dùng cuối | ⚪ | Điền số WER từ Task 12b vào bảng model |
| 14 | Nghiệm thu 6 tiêu chí + tag `v0.1.0` | ⚪ | Ghi PASS/FAIL vào bảng dưới |

## Kết quả đo WER (Task 12b — điền khi chạy)

| Model | WER | Thời gian xử lý | Ghi chú |
|---|---|---|---|
| phowhisper-small | — | — | |
| large-v3-turbo | — | — | |

## Kết quả nghiệm thu (Task 14 — điền khi chạy)

| Tiêu chí | Kết quả | Ghi chú |
|---|---|---|
| 1. Cài trên máy sạch không lỗi | — | |
| 2. `run` tự mở browser + UI tiếng Việt | — | |
| 3. File dài → DOCX/XLSX đủ timestamp, người nói, câu | — | |
| 4. Glossary sửa đúng từ khai báo | — | |
| 5. Chạy offline sau lần tải model đầu | — | |
| 6. WER trên audio mẫu thật ≤ 30% | — | Đo bằng Task 12b |

## Việc treo / rủi ro đang mở

- [ ] Verify installer trên Windows thật (chưa có máy trong phiên này)
- [ ] API sherpa-onnx / faster-whisper có thể lệch phiên bản → Task 12 sẽ phát hiện
- [ ] Chất lượng diarization với ghi âm mic chung — cần file thật của người dùng để đánh giá
- [ ] Task 12b cần người dùng cung cấp file audio thật 3–5 phút + transcript gõ tay
