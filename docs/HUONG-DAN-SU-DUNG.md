# Hướng dẫn sử dụng ViTranscript (macOS & Windows)

> Dành cho người dùng cuối và beta-tester. Hướng dẫn ngắn gọn có trong
> [`README.md`](../README.md); đây là bản đầy đủ, có khắc phục sự cố cho cả hai hệ điều hành.

ViTranscript chuyển audio/video tiếng Việt thành văn bản có timestamp, phân biệt người
nói, và xuất DOCX / Excel / SRT / TXT. **Mọi xử lý chạy trên máy bạn** — file và transcript
không tải lên server bên thứ ba. Lần đầu cần mạng để tải model; sau đó chạy offline.

---

## 1. Yêu cầu máy

| | macOS | Windows |
|---|---|---|
| Hệ điều hành | macOS 12+ (Intel hoặc Apple Silicon) | Windows 10/11 64-bit |
| Ổ trống | ~2–4 GB (model + thư viện) | ~2–4 GB |
| RAM | 8 GB trở lên (khuyến nghị) | 8 GB trở lên |
| Mạng | Chỉ cần cho **lần đầu** tải model | Chỉ cần cho **lần đầu** tải model |

Không cần cài Python hay GPU trước — script cài đặt tự lo. Không dùng dịch vụ đám mây.

---

## 2. Cài đặt

Bộ cài gồm 4 file ở thư mục gốc: `install.command`, `run.command` (macOS);
`install.bat`, `run.bat` (Windows). Chỉ chạy **install** một lần.

### macOS

1. Nhấp đúp **`install.command`**.
2. Nếu macOS báo *"không thể mở vì từ nhà phát triển không xác định"*:
   **chuột phải** vào file → **Open** → bấm **Open** lần nữa. (Chỉ cần làm lần đầu.)
3. Cửa sổ Terminal mở ra, tự cài `uv` + Python 3.12 + thư viện. Đợi tới khi thấy dòng
   báo hoàn tất, rồi đóng cửa sổ.

**Nếu gặp lỗi:**
- *"command not found" hoặc treo ở bước tải:* kiểm tra mạng, chạy lại `install.command`.
- *Quyền thực thi bị chặn:* mở Terminal, kéo file `install.command` vào cửa sổ, Enter.
- *Máy chặn theo chính sách doanh nghiệp:* liên hệ IT để cho phép chạy script `uv`.

### Windows

1. Nhấp đúp **`install.bat`**.
2. Nếu **SmartScreen** cảnh báo: bấm **More info** → **Run anyway**.
3. Nếu **Windows Defender / antivirus** hỏi: cho phép chạy (script chỉ tải `uv` + Python
   về thư mục người dùng, không sửa hệ thống).
4. Cửa sổ Command Prompt mở ra, tự cài đặt. Đợi tới khi thấy báo hoàn tất, nhấn phím
   bất kỳ để đóng.

**Nếu gặp lỗi:**
- *Cửa sổ nháy rồi tắt ngay:* mở **Command Prompt**, kéo `install.bat` vào cửa sổ,
  Enter — để đọc được thông báo lỗi.
- *"is not recognized" / lỗi tải:* kiểm tra mạng; nếu công ty chặn proxy, thử mạng khác.
- *Đường dẫn có dấu tiếng Việt:* đặt cả thư mục ViTranscript ở đường dẫn **không dấu**
  (ví dụ `C:\ViTranscript\`) để tránh lỗi mã hóa.

> ⚠️ **Beta:** đường cài Windows chưa được kiểm thử trọn vẹn trên máy thật. Nếu bạn gặp
> bất kỳ lỗi nào khi cài trên Windows, xin báo lại — xem mục 9.

---

## 3. Chạy ứng dụng

- **macOS:** nhấp đúp **`run.command`**.
- **Windows:** nhấp đúp **`run.bat`**.

Trình duyệt sẽ **tự mở** giao diện ViTranscript sau khoảng 1–2 giây, tại địa chỉ dạng
`http://127.0.0.1:8756`.

> Port có thể khác 8756 nếu port đó đang bận (app tự tìm port trống 8756–8805). Cứ để app
> tự mở trình duyệt; nếu không tự mở, xem dòng `ViTranscript đang chạy tại http://127.0.0.1:<port>`
> trong cửa sổ Terminal/Command Prompt và mở địa chỉ đó thủ công.

Ứng dụng **chỉ chạy trên máy bạn** (`127.0.0.1`), không mở ra mạng ngoài. Để tắt: đóng
cửa sổ Terminal/Command Prompt (hoặc nhấn `Ctrl+C` trong đó).

---

## 4. Dùng cơ bản — 7 bước

1. **Chọn file** audio/video (mp3, m4a, wav, mp4, …).
2. **Chọn model** (mặc định PhoWhisper Small — nhanh, tiếng Việt tốt). Lần đầu dùng một
   model, app tải model về (xem mục 5).
3. Tùy chọn: **ngôn ngữ**, **phân biệt người nói** (bật/tắt), **số người nói**
   (0 = tự đoán), **glossary**, **tự chèn dấu câu** (bật mặc định).
4. Bấm **Bắt đầu**, đợi thanh tiến trình chạy tới 100%.
5. Nếu bật diarization: **đổi tên người nói** (Người 1 → tên thật) ở phần trên.
6. **Sửa nhầm người nói** (nếu cần): mỗi dòng transcript có ô chọn lại người nói.
   > Chỉnh sửa sống trong trang — **refresh trang sẽ mất**, nên sửa xong hãy xuất file ngay.
7. **Tải kết quả**: chọn định dạng **DOCX / XLSX / SRT / TXT**.

> **Chỉ một job tại một thời điểm.** Gửi job mới khi đang xử lý → app báo bận (HTTP 409).
> Đợi job hiện tại xong rồi thử lại.

---

## 5. Model (tải lần đầu)

| Model | Dung lượng | Khi nào dùng |
|---|---|---|
| PhoWhisper Small | ~490 MB | Mặc định — nhanh, tiếng Việt tốt |
| PhoWhisper Medium | ~1.5 GB | Chính xác hơn, chậm hơn ~2× |
| PhoWhisper Large | ~3 GB | Chính xác nhất cho tiếng Việt, chậm |
| Whisper Large-v3 Turbo | ~1.6 GB | Khi xen nhiều tiếng Anh |
| Whisper Small (gốc) | ~490 MB | Đa ngôn ngữ, nhẹ |

- Lần đầu chọn một model, app **tải về máy** (cần mạng). Các lần sau chạy **offline**.
- **Phục hồi dấu câu** dùng thêm model ViBERT-CAPU ONNX ~110 MB, cũng tải một lần.

---

## 6. Tính năng nâng cao

### Phục hồi dấu câu & viết hoa
Bật mặc định, đặc biệt hữu ích với PhoWhisper. Chỉ đổi **viết hoa** và thêm **`. , : ?`** —
không đổi chính tả hay timestamp. Nếu model dấu câu không tải/chạy được, job vẫn hoàn tất
bằng transcript gốc kèm cảnh báo vàng. Tắt tùy chọn nếu muốn dùng cách tách câu cũ.

### Glossary (từ điển sửa từ)
Khai báo từ hay bị nghe nhầm (tên riêng, thuật ngữ). App sửa **đúng từ khai báo** và gợi
**từ gần đúng** (fuzzy). Ví dụ: `NVIDIA`, `Vinamilk`.

### File dài (1–4 giờ)
- File **> 2 giờ**: app tự **tắt phân biệt người nói** để tránh hết bộ nhớ — transcript và
  timestamp vẫn đầy đủ (có ghi chú vàng trên màn hình).
- File **> 4 giờ**: app từ chối, khuyên cắt nhỏ.
- Nếu app tắt giữa chừng (mất điện, đóng nhầm): mở lại app, phần transcript đã xong **tự
  hiện lại** — có thể xuất ngay, hoặc chạy lại từ đầu để có bản đầy đủ.

---

## 7. Nơi lưu dữ liệu

| | Đường dẫn |
|---|---|
| macOS | `~/Library/Application Support/ViTranscript/` |
| Windows | `%APPDATA%\ViTranscript\` (tức `C:\Users\<tên>\AppData\Roaming\ViTranscript\`) |

Bên trong: `models/` (model đã tải), `punctuation/` (model dấu câu), `jobs/` (kết quả từng
lần chạy), `settings.json`, `glossary.txt`.

> **Dọn đĩa:** bản beta **không tự xóa** thư mục `jobs/`. Nếu đầy đĩa, xóa thủ công các
> thư mục con trong `jobs/` (mỗi thư mục là một lần chạy).

---

## 8. Khắc phục sự cố chung

| Triệu chứng | Cách xử lý |
|---|---|
| Trình duyệt không tự mở | Đọc dòng `ViTranscript đang chạy tại http://127.0.0.1:<port>` trong Terminal/CMD, mở địa chỉ đó |
| "Đang có job chạy" (409) | Đợi job hiện tại xong, hoặc tải lại trang khi thanh tiến trình đã 100% |
| Tải model chậm/lỗi | Kiểm tra mạng; model lớn (1–3 GB) cần thời gian; thử lại `run` |
| Kết quả sai nhiều | Thử model lớn hơn (Medium/Large); khai báo glossary; kiểm tra chất lượng ghi âm |
| Tách người nói sai | Diarization phụ thuộc chất lượng thu; mic chung dễ sai — tắt diarization nếu không cần |
| Mất chỉnh sửa người nói | Đừng refresh trang trước khi tải file; chỉnh xong xuất ngay |
| Cổng/tường lửa hỏi quyền | Chỉ cần cho phép **localhost** — app không mở ra mạng ngoài |

---

## 9. Dành cho beta-tester

Bản `v0.1.0-beta` còn vài mục **chưa nghiệm thu đầy đủ**. Xin ưu tiên thử và phản hồi:

- **Cài + chạy trên Windows thật** (mục cần nhất — chưa từng verify trọn vẹn).
- **File dài thật** (30 phút – vài giờ): transcript, timestamp, xuất file có đúng không?
- **Chạy offline**: sau khi đã tải model, tắt mạng và thử lại một lần.
- **Độ chính xác** trên giọng/chủ đề của bạn: sai nhiều ở đâu, từ nào hay nhầm?

**Cách báo lỗi** — mở issue trên GitHub kèm:
1. Hệ điều hành + phiên bản (vd: Windows 11, macOS 14 Apple Silicon).
2. Các bước tái hiện.
3. Thông báo lỗi (với lỗi cài Windows: **copy toàn bộ nội dung cửa sổ `install.bat`**).
4. Loại file, độ dài, model đã chọn.

Giới hạn đã biết đầy đủ: [`docs/RELEASE-NOTES-v0.1.0-beta.md`](RELEASE-NOTES-v0.1.0-beta.md).

---

## 10. Gỡ cài đặt

Xóa dữ liệu runtime: xóa thư mục trong mục 7. Xóa ứng dụng: xóa thư mục ViTranscript đã
giải nén. `uv`/Python do script tải nằm trong thư mục người dùng của `uv` (macOS/Linux:
`~/.local`; Windows: thư mục cài `uv`) — xóa nếu không dùng cho việc khác.
