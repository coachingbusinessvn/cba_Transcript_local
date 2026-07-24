# Tasks — Chịu tải file dài

> Bảng theo dõi thực thi. Chi tiết từng task (file, interface, code đầy đủ, lệnh verify) xem [04-plan-long-audio.md](04-plan-long-audio.md). Bối cảnh: review 2026-07-18 chỉ ra 3 điểm gãy với file dài — OOM khi đọc WAV cho diarization, crash mất trắng transcript, không có chặn đầu vào quá dài.
>
> **Quy trình mỗi task:** code → `uv run ruff check .` sạch → chạy verify của task → commit (trailer `Co-Authored-By: Claude Fable 5`). Xem Global Constraints trong plan.
>
> **Phạm vi:** 3 lớp bảo vệ A (checkpoint từng phần) + B (giảm đỉnh RAM) + C (chính sách thời lượng). **Ngoài phạm vi:** transcribe theo cửa sổ + resume từ checkpoint (cần brainstorm stitching speaker-ID — làm nhánh sau).

**Trạng thái:** 🟢 xong (đã verify + commit) · 🔵 đang làm · ⚪ chưa làm

| # | Task | Lớp | Trạng thái | Ghi chú |
|---|------|-----|-----------|---------|
| 1 | Đọc WAV theo khối — giảm ~2.5× đỉnh RAM (`app/media.py`) | B | 🟢 | Giữ nguyên chữ ký, thêm `_chunk_frames` |
| 2 | `media.duration_seconds` qua ffprobe | C | 🟢 | Trả `None` nếu không đọc được, không raise |
| 3 | Module checkpoint JSONL (`app/checkpoint.py`) | A | 🟢 | Parser chịu được dòng cuối bị cắt dở |
| 4 | Nối checkpoint vào transcribe + pipeline (`segment_cb`, `partial.jsonl`) | A | 🟢 | Xóa partial cũ khi job bắt đầu |
| 5 | Server: policy file dài + khôi phục kết quả một phần + export partial | A+C | 🟢 | Ngưỡng: 4h từ chối, 2h tắt diarize; job dict thêm `model`/`note` |
| 6 | UI: hiển thị note vàng + render kết quả một phần khi error | A+C | 🟢 | `noteBox`; error + result → vẫn showResults |
| 7 | README mục "File dài" + nghiệm thu file thật ≥ 2h | docs | 🟢 | Unit/integration pass; file thật ≥ 2h cần người dùng |


## Nghiệm thu file dài (Task 7 — điền khi chạy)

| Tiêu chí | Kết quả | Ghi chú |
|---|---|---|
| 1. File > 2h: note vàng hiện, job chạy hết không OOM | ⏳ | Cần file thật ≥ 2h từ người dùng |
| 2. Kill process giữa chừng → mở lại thấy kết quả một phần, xuất DOCX được | ✅ unit | `test_get_job_recovers_partial_from_disk` |
| 3. File > 4h bị từ chối kèm hướng dẫn cắt file | ✅ unit | `test_long_audio_policy` (5h → 400) |
| 4. File ngắn (< 2h): hành vi y như trước, không note | ✅ unit | policy 10 phút giữ nguyên |


## Việc treo / rủi ro đang mở

- [ ] Nghiệm thu cần file thật ≥ 2 giờ từ người dùng (chưa có trong repo — `.gitignore` chặn `eval/sample.*`)
- [ ] Ngưỡng 2h/4h là ước lượng an toàn cho máy 8 GB RAM — cân chỉnh lại sau khi đo thực tế trên máy người dùng
- [ ] Sherpa-onnx vẫn giữ bản sao samples nội bộ khi diarize — lớp B chỉ giảm phần Python; nếu vẫn OOM với file 2h thì hạ `_MAX_DIARIZE_SECONDS`
- [ ] Chunked transcribe + resume (lớp D/E) — nhánh riêng, cần brainstorm stitching speaker-ID giữa các cửa sổ
