# Hướng dẫn Sử dụng ViTranscript Desktop

> **ViTranscript Desktop** là ứng dụng **chạy hoàn toàn trên máy tính của bạn (Local-first)**, hỗ trợ chuyển đổi file âm thanh/video ghi âm hội thoại tiếng Việt thành văn bản transcript có định giờ (timestamp), phân biệt người nói, phục hồi dấu câu và xuất ra các định dạng DOCX, Excel, SRT, TXT.
> 
> **Đặc điểm nổi bật bản Desktop:**
> - Giao diện cửa sổ ứng dụng độc lập (Native Window), **không mở trình duyệt web ngoài, không mở cửa sổ dòng lệnh Terminal**.
> - Bảo mật dữ liệu tuyệt đối: File âm thanh và văn bản **không bao giờ bị tải lên internet**.
> - Chạy **offline 100%** sau lần tải model đầu tiên.

---

## 1. Cài đặt Ứng dụng

### 1.1 Ubuntu Linux

Dự án cung cấp 2 định dạng cài đặt cho Linux:

#### Cách 1: Sử dụng file `.AppImage` (Khuyên dùng — Không cần cài đặt)
1. Tải file `ViTranscript_x86_64.AppImage` về máy.
2. Mở Terminal tại thư mục chứa file và cấp quyền thực thi:
   ```bash
   chmod +x ViTranscript_x86_64.AppImage
   ```
3. Nhấp đúp vào file `.AppImage` để chạy ứng dụng trực tiếp.
4. *Lưu ý về FUSE:* Nếu hệ thống Ubuntu của bạn chưa có thư viện FUSE (thường gặp trên Ubuntu 22.04 LTS trở lên), bạn có thể chạy qua dòng lệnh bằng cách thêm cờ `--appimage-extract-and-run`:
   ```bash
   ./ViTranscript_x86_64.AppImage --appimage-extract-and-run
   ```

#### Cách 2: Cài đặt gói `.deb`
1. Tải file `vitranscript_amd64.deb`.
2. Nhấp đúp vào file `.deb` để cài đặt qua **Ubuntu Software Center**, hoặc chạy lệnh trong Terminal:
   ```bash
   sudo apt install ./vitranscript_amd64.deb
   ```
3. Sau khi cài xong, tìm và mở **ViTranscript** từ danh sách ứng dụng (Application Launcher) của hệ thống.

---

### 1.2 macOS (`.dmg`) & Windows (`.exe` / NSIS)

> [!NOTE]
> **Trạng thái phát hành:** **CHỜ VERIFY MÁY THẬT**  
> Bộ cài đặt dành cho macOS (`.dmg` / `.app`) và Windows (`.exe` / NSIS Installer) đã được đóng gói tự động thành công trên hệ thống CI. Tuy nhiên, tính năng này đang chờ nghiệm thu trực tiếp trên thiết bị macOS và Windows thật trước khi phát hành chính thức.

- **macOS:** Tải file `.dmg`, mở đĩa ảo và kéo `ViTranscript.app` vào thư mục `Applications`.
- **Windows:** Tải file `ViTranscript-Setup.exe` và nhấp đúp để thực hiện cài đặt qua trình hướng dẫn (Setup Wizard).

---

## 2. Xử lý Cảnh báo An ninh cho Bản dựng Chưa ký số (Unsigned Artifact)

Do ứng dụng chưa được mua chứng thư ký số thương mại từ Apple hoặc Microsoft, hệ điều hành có thể hiển thị cảnh báo an toàn khi bạn mở ứng dụng lần đầu.

### 2.1 Môi trường macOS (Cảnh báo Gatekeeper)

Khi mở ứng dụng lần đầu, macOS có thể báo: *“ViTranscript.app không thể mở vì từ nhà phát triển không xác định”*.

**Cách vượt cảnh báo:**
1. Mở thư mục `Applications` trong Finder.
2. **Nhấp chuột phải** (hoặc giữ phím `Control` và nhấp chuột) vào ứng dụng **ViTranscript** -> chọn **Open**.
3. Một hộp thoại xác nhận hiện ra, nhấp vào nút **Open** lần nữa. Sau này bạn có thể nhấp đúp mở ứng dụng bình thường.
4. *Cách nâng cao:* Mở ứng dụng Terminal và chạy lệnh xóa thuộc tính kiểm duyệt quarantine:
   ```bash
   xattr -cr /Applications/ViTranscript.app
   ```

### 2.2 Môi trường Windows (Cảnh báo SmartScreen)

Khi chạy file cài đặt hoặc file thực thi trên Windows, cửa sổ **Windows Protected Your PC (SmartScreen)** có thể xuất hiện.

**Cách vượt cảnh báo:**
1. Nhấp vào dòng chữ **More info** (Thông tin thêm) ở bên dưới thông báo.
2. Nhấp vào nút **Run anyway** (Vẫn tiếp tục chạy) vừa xuất hiện ở góc dưới.

---

## 3. Lần đầu Tải Model & Chế độ Offline

- **Khởi chạy lần đầu tiên:** Ứng dụng cần có kết nối mạng Internet để tải các model nhận dạng giọng nói (PhoWhisper/Whisper), model phân biệt người nói (Diarization ~30 MB) và model phục hồi dấu câu (ViBERT-CAPU ~110 MB) từ Hugging Face về đĩa cứng. Dung lượng model nhận dạng dao động từ ~490 MB (small) đến ~3 GB (large) tùy thuộc vào model bạn chọn (có thể cộng thêm ~140 MB cho diarization và dấu câu).
- **Các lần khởi chạy sau:** Sau khi model đã được tải về máy thành công, ứng dụng hoạt động **hoàn toàn offline**. Bạn có thể tắt kết nối Wifi/Mạng internet mà ứng dụng vẫn chuyển đổi văn bản bình thường.

---

## 4. Hướng dẫn Sử dụng Chi tiết

### 4.1 Khởi chạy & Giao diện Chính
Nhấp đúp biểu tượng ứng dụng **ViTranscript**. Cửa sổ native sẽ hiện lên ngay lập tức. Bạn không cần gõ lệnh Terminal hay mở trình duyệt web.

### 4.2 Thêm File Audio/Video & Hàng chờ (Queue)
Bạn có thể chọn file bằng các cách sau:
- Vào menu ứng dụng: Chọn **File > Mở…**.
- Hoặc bấm nút **Chọn file audio / video** trên màn hình.
- Hoặc **kéo-thả trực tiếp** một hoặc nhiều file từ máy tính vào trong cửa sổ ứng dụng.

> [!TIP]
> **Tính năng Hàng chờ (Queue):**  
> Khi bạn chọn hoặc kéo-thả **nhiều file cùng lúc**, ứng dụng sẽ tự động xếp các file vào danh sách hàng chờ và **xử lý tuần tự từng file một** (đảm bảo không bị quá tải bộ nhớ RAM). Bạn có thể theo dõi trạng thái từng file (`Chờ xử lý`, `Đang chạy`, `Hoàn tất`, `Lỗi`).

### 4.3 Thiết lập Tham số Nhận dạng
Trước khi bấm nút **Bắt đầu**, bạn có thể tùy chỉnh các thông số:

1. **Chọn Model:**
   - `phowhisper-small` *(Mặc định — Khuyên dùng)*: Tốc độ nhanh, nhận dạng tiếng Việt rất tốt, dung lượng nhẹ (~490 MB).
   - `phowhisper-medium`: Chính xác hơn small, tốc độ trung bình (~1.5 GB).
   - `phowhisper-large`: Độ chính xác cao nhất cho tiếng Việt, chậm hơn, cần máy có RAM từ 8 GB trở lên (~3 GB).
   - `large-v3-turbo`: Phù hợp cho các buổi họp song ngữ Việt - Anh (~1.6 GB).
   - `whisper-small`: Model Whisper Small gốc đa ngôn ngữ, nhẹ (~490 MB).
2. **Ngôn ngữ:** Mặc định `Tiếng Việt` (`vi`).
3. **Phân biệt người nói (Diarization):** Bật tùy chọn này để ứng dụng tự động gán nhãn `Người nói 1`, `Người nói 2`...
4. **Số người nói:** Để `0` nếu muốn ứng dụng tự đoán số lượng người tham gia hội thoại.
5. **Tự chèn dấu câu:** Tự động phục hồi viết hoa và các dấu `. , : ?` giúp bản gõ chuẩn hóa dễ đọc hơn.
6. **Từ điển sửa lỗi (Glossary):** Khai báo các từ khóa tên riêng hoặc quy tắc thay thế (ví dụ: `vina milk => Vinamilk`).

### 4.4 Xuất Kết quả
Sau khi thanh tiến trình chạy xong 100%:
- Bạn có thể **đổi tên nhãn người nói** hoặc điều chỉnh lại dòng ghi âm trực tiếp trên giao diện.
- Bấm vào các nút xuất file tương ứng để tải bản kết quả về máy:
  - **DOCX (Word):** Bảng transcript đẹp có timestamp và màu phân biệt người nói.
  - **XLSX (Excel):** Phù hợp để phân tích dữ liệu hội thoại.
  - **SRT:** File phụ đề cho video.
  - **TXT:** File văn bản thuần.

### 4.5 Thoát Ứng dụng
Khi dùng xong, bạn chỉ cần bấm nút đóng cửa sổ (dấu `X`) hoặc chọn menu **File > Thoát**.  
Toàn bộ dịch vụ xử lý chạy ngầm sẽ được tắt sạch sẽ khỏi hệ thống (ứng dụng **không** chạy ẩn dưới khay hệ thống / System Tray).

---

## 5. Đường dẫn Dữ liệu & File Log trên Máy

Tất cả các model đã tải, cài đặt người dùng, từ điển glossary và file log được lưu trữ tại thư mục dữ liệu cá nhân theo quy chuẩn của từng hệ điều hành:

| Hệ điều hành | Đường dẫn lưu dữ liệu & Log |
|---|---|
| **macOS** | `~/Library/Application Support/ViTranscript/` |
| **Windows** | `%APPDATA%\ViTranscript\` *(ví dụ `C:\Users\<TênUser>\AppData\Roaming\ViTranscript\`)* |
| **Linux (Ubuntu)** | `~/.local/share/ViTranscript/` *(hoặc `$XDG_DATA_HOME/ViTranscript/`)* |

- **Thư mục Log:** `.../ViTranscript/logs/` (nếu ứng dụng gặp lỗi, bạn có thể kiểm tra file log tại đây để biết chi tiết).
- **Reset ứng dụng:** Nếu bạn muốn xóa toàn bộ model đã tải để giải phóng dung lượng đĩa cứng, bạn chỉ cần xóa thư mục `ViTranscript` ở đường dẫn trên.

---

## 6. Hướng dẫn Gỡ cài đặt (Uninstall)

### Ubuntu Linux
- **Bản `.deb`:** Mở Terminal và gõ lệnh:
  ```bash
  sudo apt remove vitranscript
  ```
- **Bản `.AppImage`:** Chỉ cần xóa file `.AppImage` đã tải về.

### macOS
Mở Finder -> Thư mục `Applications` -> Kéo file `ViTranscript.app` vào Thùng rác (Trash).

### Windows
Vào **Settings** -> **Apps** -> **Installed Apps** -> Tìm **ViTranscript** -> Chọn **Uninstall**.
