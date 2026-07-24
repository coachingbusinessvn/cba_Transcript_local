# Tasks — Chọn lại người nói từng dòng

> Bảng theo dõi thực thi. Spec: [06-spec-speaker-reselect.md](06-spec-speaker-reselect.md) · Plan chi tiết (code đầy đủ, verify): [07-plan-speaker-reselect.md](07-plan-speaker-reselect.md).
>
> **Quy trình mỗi task:** code → `uv run ruff check .` sạch → verify của task → commit (trailer `Co-Authored-By: Claude Fable 5`).
>
> **Quyết định đã chốt:** client-side only (mất khi refresh — chấp nhận) · chỉ speaker diarization phát hiện được · dropdown luôn hiển thị.
>
> **Xung đột biết trước:** plan long-audio ([05-tasks-long-audio.md](05-tasks-long-audio.md) Task 5) cũng sửa `export_job` — plan nào chạy sau giữ nguyên thay đổi của plan trước.

**Trạng thái:** 🟢 xong (đã verify + commit) · 🔵 đang làm · ⚪ chưa làm

| # | Task | Trạng thái | Ghi chú |
|---|------|-----------|---------|
| 1 | Server: `_apply_speaker_overrides` + body export nhận `speakers` | 🟢 | Best-effort, entry rác bỏ qua êm, không 400 |
| 2 | UI: dropdown mỗi dòng + `collectSpeakerOverrides` gửi kèm export | 🟢 | Option tính 1 lần tại `showResults`; đổi tên → nhãn cập nhật |
| 3 | README + cập nhật bảng này | 🟢 | |

## Nghiệm thu (điền khi chạy)

| Tiêu chí | Kết quả | Ghi chú |
|---|---|---|
| 1. Mỗi dòng có speaker hiện dropdown; dòng không speaker giữ text rỗng | ✅ code | `spk-select` khi có speakerIds; text rỗng khi null |
| 2. Đổi speaker 1 dòng → export SRT/DOCX phản ánh đúng | ✅ unit | `test_export_srt_with_speaker_override` |
| 3. Đổi tên người nói → nhãn trong mọi dropdown cập nhật, lựa chọn giữ nguyên | ✅ code | `renderPreview` dùng `speakerLabel` |
| 4. Gán lại hết dòng của 1 speaker → speaker đó vẫn còn trong dropdown các dòng khác | ✅ code | `speakerIds` snapshot tại `showResults` |
| 5. File không diarization: không dropdown, export như cũ (regression) | ✅ code | `!speakerIds.length` → text |


## Việc treo / rủi ro đang mở

- [ ] Chỉnh sửa mất khi refresh — nếu người dùng phàn nàn, nâng cấp sau: POST override lên server ghi vào status.json (đổi quyết định 1)
- [ ] Chỉ 300 dòng đầu sửa được (giới hạn render sẵn có) — file rất dài cần phân trang, để nhánh sau
