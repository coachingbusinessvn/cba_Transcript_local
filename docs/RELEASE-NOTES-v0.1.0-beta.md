# ViTranscript v0.1.0-beta

**Ngày phát hành:** 2026-07-24
**Trạng thái:** Beta — dùng được cho công việc thật, nhưng còn vài mục chưa nghiệm thu đầy đủ (xem *Giới hạn đã biết*).

ViTranscript chuyển hội thoại tiếng Việt (audio/video) thành văn bản có timestamp,
phân biệt người nói, và xuất DOCX / Excel / SRT / TXT. **Mọi xử lý chạy trên máy của
bạn** — file ghi âm và transcript không tải lên server bên thứ ba. Lần đầu cần mạng để
tải model; sau đó chạy offline.

---

## Có gì trong bản beta này

- **Transcript tiếng Việt** bằng PhoWhisper (faster-whisper, CPU, không cần GPU/PyTorch).
- **Phân biệt người nói** (diarization) bằng sherpa-onnx, đổi tên người nói trước khi xuất.
- **Phục hồi dấu câu & viết hoa** tự động (ViBERT-CAPU ONNX INT8) — bật mặc định, chỉ đổi
  hoa/thường và thêm `. , : ?`, không đổi chính tả hay timestamp. Tải model ~110 MB lần đầu.
- **Glossary 2 tầng**: sửa đúng từ khai báo (exact) + gợi từ gần đúng (fuzzy).
- **Xuất DOCX / XLSX / SRT / TXT**.
- **Hỗ trợ file dài**: tự tắt diarization khi file >2 giờ; từ chối file >4 giờ; tự khôi phục
  transcript dở nếu app bị tắt giữa chừng.
- **Giao diện web tiếng Việt**, chạy hoàn toàn ở `127.0.0.1` (không mở ra mạng ngoài).
- **Một job tại một thời điểm** (trả HTTP 409 nếu gửi job khi đang bận).

## Đã kiểm chứng

- 66 unit test pass (1 deselected), ruff sạch.
- App khởi động, `/api/meta` trả 200, model mặc định `phowhisper-small` + model dấu câu
  chạy được (kể cả offline với model đã cache).
- Smoke E2E trên macOS (audio ngắn) tạo được DOCX/XLSX đầy đủ.

---

## Cài đặt

**macOS:** nhấp đúp `install.command` (nếu bị chặn: chuột phải → Open → Open).
**Windows:** nhấp đúp `install.bat` (nếu SmartScreen cảnh báo: More info → Run anyway).

## Chạy

Nhấp đúp `run.command` (Mac) hoặc `run.bat` (Windows) → trình duyệt mở giao diện tại
`http://127.0.0.1:8765`. Hướng dẫn đầy đủ: [`README.md`](../README.md).

---

## ⚠️ Giới hạn đã biết (đọc trước khi báo lỗi)

- **Windows chưa được verify trên máy thật.** `install.bat`/`run.bat` đã viết nhưng
  chưa từng chạy trọn vẹn trên một máy Windows sạch trong quá trình phát triển. Nếu bạn
  test trên Windows, đây là mục **cần phản hồi nhất** — báo lại mọi lỗi khi cài/chạy.
- **File rất dài chưa thử.** Đường xử lý file ~30 phút–4 giờ đã có code nhưng mới chỉ
  smoke bằng audio ngắn. File dài thật (đặc biệt >2 giờ) là thứ cần beta-tester thử.
- **Chưa đo WER (độ chính xác) trên audio thật.** Cần bạn cung cấp file mẫu + bản gõ tay
  để đo. Chất lượng transcript có thể dao động theo chất lượng ghi âm.
- **Diarization với mic chung** (nhiều người thu chung một micro) có thể tách người nói
  không chính xác — phụ thuộc chất lượng thu.
- **Offline chưa test có hệ thống.** Model dấu câu đã xác nhận chạy offline; toàn bộ
  pipeline khi tắt hẳn mạng thì chưa kiểm tra kỹ.
- **Chưa tự dọn đĩa.** Thư mục job không tự xóa; xóa thủ công theo đường dẫn data trong README.

## Cách gửi phản hồi

Mở issue trên GitHub kèm: hệ điều hành (macOS/Windows + phiên bản), bước tái hiện, và
thông báo lỗi (nếu có). Với lỗi cài đặt Windows, kèm toàn bộ output cửa sổ `install.bat`.

---

## Lộ trình lên GA `v0.1.0`

Sẽ gắn khi đủ 6 tiêu chí nghiệm thu PASS trên máy sạch (gồm Windows) — xem bảng trong
[`docs/03-tasks.md`](03-tasks.md).
