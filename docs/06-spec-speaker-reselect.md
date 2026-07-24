# Spec: Chọn lại người nói cho từng dòng transcript

> Thiết kế đã chốt qua brainstorm 2026-07-18. Plan thực thi: [07-plan-speaker-reselect.md](07-plan-speaker-reselect.md).

## Vấn đề

Diarization tự động gán nhầm người nói ở một số dòng (đặc biệt ghi âm mic chung, người nói chen nhau). Hiện tại người dùng không sửa được — cột "Người nói" trong bảng xem trước là text tĩnh, và file xuất ra giữ nguyên nhãn sai.

## Quyết định thiết kế (đã chốt với người dùng)

1. **Client-side only** — thay đổi sống trong browser, gửi kèm request export. KHÔNG lưu server, KHÔNG ghi status.json. Refresh trang là mất chỉnh sửa (chấp nhận).
2. **Chỉ speaker có sẵn** — dropdown chỉ liệt kê các speaker mà diarization đã phát hiện. KHÔNG có "thêm người nói mới".
3. **Dropdown luôn hiển thị** (approach 1) — ô "Người nói" của mỗi dòng là `<select>` thay vì text; không cần click-to-edit.

## Hành vi

### UI (`app/static/index.html`)

- Mỗi dòng trong bảng xem trước có `speaker != null` → ô "Người nói" render `<select>`; option = danh sách speaker ID phát hiện được, nhãn qua `speakerLabel()` (tên tự đặt hiển thị đúng).
- Danh sách option tính **một lần** tại `showResults` từ kết quả gốc và tái sử dụng — gán lại dòng cuối của một speaker không làm speaker đó biến mất khỏi dropdown của các dòng khác.
- Đổi lựa chọn → cập nhật `sentences[i].speaker` tại chỗ (mảng client).
- Đặt/đổi tên người nói (ô nhập sẵn có) → re-render bảng → nhãn option cập nhật theo, lựa chọn hiện tại giữ nguyên.
- Dòng không có speaker (tắt diarization) → giữ text rỗng như cũ, không dropdown.

### Export (`app/server.py`)

- Body export thêm key tùy chọn `speakers: {"<index_câu>": <speaker_id>}` — chỉ chứa các dòng THAY ĐỔI so với kết quả gốc.
- Server áp override vào bản sao sentences trước khi dựng DOCX/XLSX/SRT/TXT. Kiểm tra: index trong biên, speaker_id thuộc tập speaker có trong kết quả gốc, dòng gốc có speaker; entry không hợp lệ bị bỏ qua êm (không 400 — override là best-effort).
- Không thay đổi gì khác phía server. Không persist.

## Giới hạn chấp nhận

- Mất chỉnh sửa khi refresh trang / mở lại job (hệ quả quyết định 1).
- Chỉ 300 dòng đầu của bảng xem trước sửa được (giới hạn render sẵn có — không đổi trong phạm vi này).
- Không sửa được text câu, không gộp/tách câu (ngoài phạm vi).

## Kiểm thử

- Unit: hàm áp override phía server (hợp lệ, ngoài biên, speaker lạ, kiểu dữ liệu rác).
- Integration: TestClient export SRT với override → nội dung file phản ánh speaker mới.
- UI: kiểm tra tay trong browser (dropdown hiện, đổi speaker, đổi tên, export đúng).
