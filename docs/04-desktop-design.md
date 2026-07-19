# Thiết kế: Vỏ desktop cho ViTranscript (v1.5)

> Design doc đã chốt với người dùng ngày 2026-07-19. Bổ sung cho [01-bai-toan.md](01-bai-toan.md) và [02-plan.md](02-plan.md); triển khai **sau khi Task 14 (nghiệm thu v1) hoàn tất**.
> Bản implementation-ready nằm tại `docs/09-spec-desktop-shell.md`, tracker tại
> `docs/10-tasks-desktop-shell.md` trên worktree implementation. Tài liệu này giữ vai
> trò tóm tắt quyết định sản phẩm.

## 1. Bối cảnh & quyết định đã chốt

Người dùng muốn app "desktop" trên Mac + Windows. Qua thảo luận đã chốt:

| Câu hỏi | Quyết định | Lý do |
|---|---|---|
| Mục tiêu chính | Cài đặt 1 chạm thật sự (không terminal, không cần biết Python) | Audience không rành công nghệ |
| Cửa sổ native riêng? | Không cần — UI vẫn mở bằng trình duyệt | Người dùng xác nhận không ưu tiên |
| Ký số (Gatekeeper/SmartScreen) | Không ký — kèm hướng dẫn ảnh tiếng Việt để vượt cảnh báo 1 lần | Tiết kiệm $99–500/năm; số máy ít |
| Đóng gói PyInstaller? | **Không.** Đích cuối là script `uv` (Task 11) + vỏ desktop | Rẻ hơn hẳn, tránh rủi ro PyInstaller với thư viện native; chấp nhận lần cài đầu thấy terminal + cần mạng |
| Gỡ cài đặt | Phải có script gỡ **sạch**, xóa cả model đã tải (0.5–3GB) | Yêu cầu bổ sung của người dùng |

**Không đổi kiến trúc v1:** vẫn FastAPI + 1 trang HTML, server bind `127.0.0.1`, model tải lần đầu về data dir. Toàn bộ phần này chỉ là lớp vỏ quanh `python -m app.server`.

## 2. Thành phần

### 2.1 Vỏ Mac: `ViTranscript.app` bundle thủ công

- Bundle tối giản tự tạo (KHÔNG PyInstaller): thư mục `ViTranscript.app/Contents/` gồm `Info.plist`, `MacOS/launcher` (shell script), `Resources/icon.icns`.
- `install.command` **sinh** bundle này (nhúng đường dẫn tuyệt đối thư mục cài vào launcher script) rồi copy vào `/Applications`.
- Double-click app: launcher chạy `<install_dir>/.venv/bin/python -m app.server` qua
  `nohup`, **không mở Terminal**, không phụ thuộc PATH/uv lúc dùng hằng ngày. Bootstrap
  log ghi vào `<data_dir>/logs/launcher.log`, app log vào
  `<data_dir>/logs/server.log`.

### 2.2 Vỏ Windows: shortcut + chạy ẩn console

- `install.bat` tạo shortcut `.lnk` trên Desktop + Start Menu (qua PowerShell), icon `.ico`.
- Shortcut trỏ tới một VBS wrapper để **không hiện cửa sổ console** khi chạy (dự phòng nếu antivirus chặn VBS: trỏ thẳng `.venv\Scripts\pythonw.exe -m app.server` — xem bảng rủi ro mục 6).
- File `.bat` giữ quy ước không dấu (Global Constraint plan v1).

### 2.3 Icon khay hệ thống (chỗ để "Thoát")

- Dùng `pystray` (+ Pillow) trong process server: menu bar icon trên Mac, system tray trên Windows.
- Menu 2 mục: **"Mở giao diện"** (mở browser tới URL server) và **"Thoát"** (shutdown uvicorn + kết thúc process).
- Lý do bắt buộc: app chạy ẩn không console thì người dùng cần một chỗ nhìn thấy được để biết app đang chạy và tắt nó; nếu không, đóng tab browser xong process treo ngầm vô hạn.
- Lưu ý kỹ thuật cho plan: trên macOS pystray phải chạy ở **main thread** (AppKit) → uvicorn chuyển sang thread phụ; kiến trúc `app/server.py` hiện tại cần chỉnh nhỏ ở hàm `main`.

### 2.4 Gỡ cài đặt sạch: `uninstall.command` / `uninstall.bat`

Chạy theo trình tự, có xác nhận trước khi xóa:

1. Dừng server nếu đang chạy bằng `server-state.json`: PID sống chỉ được dừng sau khi
   endpoint loopback `/api/runtime` xác nhận đúng app + instance ID + PID + port.
   Không dùng `pkill -f`, không kill theo tên process.
2. In dung lượng sẽ giải phóng, hỏi xác nhận **1 lần**, rồi xóa:
   - Data dir: `~/Library/Application Support/ViTranscript` / `%APPDATA%\ViTranscript` — gồm **model đã tải**, jobs, settings, glossary, logs.
   - `/Applications/ViTranscript.app` (Mac) / shortcuts Desktop + Start Menu (Windows).
   - `.venv` trong thư mục cài.
3. Hỏi xác nhận **thứ 2 (tùy chọn)**: xóa luôn executable `uv`/`uvx` và đúng thư
   mục Python mà `uv python dir` xác nhận. Mặc định GIỮ và prompt cảnh báo đây là tool
   dùng chung; không xóa một path suy đoán hoặc toàn bộ home/cache rộng.
4. Kết thúc: nhắc người dùng xóa nốt thư mục cài (thư mục chứa chính script — script tự xóa thư mục cha có rủi ro trên Windows, để người dùng kéo vào Thùng rác là bước an toàn nhất).

### 2.5 Cập nhật README (mở rộng Task 13)

- Mục cài đặt: thêm ảnh chụp màn hình từng bước vượt Gatekeeper (chuột phải → Open; macOS mới: System Settings → Privacy & Security → Open Anyway) và SmartScreen (More info → Run anyway).
- Mục mới "Gỡ cài đặt": double-click `uninstall`, giải thích 2 câu hỏi xác nhận.

### 2.6 Một instance duy nhất

- Mỗi user profile chỉ có một server/tray ViTranscript.
- Runtime state ở `<data_dir>/server-state.json`, tạo theo exclusive-create và có
  `instance_id`, PID, port, install dir, thời điểm start.
- Double-click icon lần hai xác minh `/api/runtime`, mở browser tới port cũ rồi process
  mới tự kết thúc; không sinh server/tray thứ hai.
- State stale được phục hồi; cleanup chỉ xóa state có đúng `instance_id` của process.
- Browser chỉ mở sau khi uvicorn báo đã sẵn sàng, tránh trang connection-refused.

## 3. Trải nghiệm đích

- **Cài (1 lần):** tải zip → giải nén → double-click `install` → (vượt cảnh báo theo ảnh) → terminal chạy vài phút (cần mạng) → xong, có icon app.
- **Dùng hằng ngày:** double-click icon (Applications / Desktop) → không terminal, không console → browser mở UI → làm việc → tắt bằng tray "Thoát" hoặc cứ để chạy.
- **Gỡ:** double-click `uninstall` → xác nhận → máy sạch (kể cả model GB).

## 4. Out-of-scope (đã cân nhắc và loại)

- **PyInstaller/DMG/Inno Setup/CI build 3 nền tảng** — loại theo quyết định người dùng; nếu tương lai cần (người dùng lạ, máy không mạng lúc cài) thì đây là bước nâng cấp độc lập, không phá vỡ gì trong thiết kế này (launcher + tray dùng lại được).
- **Ký số/notarize** — lối cắm: nếu sau này trả $99, chỉ thêm bước `codesign`/`notarytool` cho `.app`; script install không đổi.
- **Auto-update** — cập nhật = tải zip mới đè lên, chạy lại `install`.
- **Cửa sổ native (pywebview)** — người dùng xác nhận không cần.

## 5. Tiêu chí nghiệm thu

1. **Mac:** sau `install.command`, có `ViTranscript.app` trong Applications; double-click → KHÔNG hiện Terminal, browser mở UI, có icon menu bar với mục Thoát.
2. **Windows:** sau `install.bat`, có shortcut Desktop + Start Menu; double-click → KHÔNG hiện console, browser mở UI, có icon tray với mục Thoát.
3. Đóng tab browser → app vẫn chạy, "Mở giao diện" từ tray mở lại đúng URL; "Thoát" → process kết thúc thật (kiểm tra bằng `ps`/Task Manager).
4. Double-click icon lần hai → PID/port không đổi, browser mở lại instance cũ.
5. **Uninstall:** chạy script gỡ → sau xác nhận, biến mất: data dir (kể cả model), app/shortcut, `.venv`. Chọn cả xác nhận 2 → chỉ uv + Python uv-managed đã xác minh biến mất.
6. Cài lại ngay sau khi gỡ → hoạt động bình thường (chứng minh gỡ không để rác chặn cài mới).

## 6. Rủi ro

| Rủi ro | Đối sách |
|---|---|
| pystray trên macOS đòi main thread, xung đột cách chạy uvicorn hiện tại | Ghi rõ trong plan: uvicorn xuống thread phụ khi có tray; smoke test Task 12 chạy lại |
| GUI app không load shell profile/PATH | Daily launcher dùng đường dẫn tuyệt đối tới Python trong `.venv`, không gọi `uv` |
| VBS wrapper bị antivirus nghi ngờ | Phương án dự phòng: shortcut trỏ thẳng `pythonw.exe` của `.venv` |
| Người dùng xóa thư mục cài trước, mất script uninstall | README mục Troubleshooting đã in sẵn đường dẫn data dir để xóa tay |
| macOS bản mới siết thêm app chưa ký | Cập nhật ảnh hướng dẫn theo OS; lối thoát ký số ghi ở mục 4 |
| Double-click nhiều lần tạo nhiều server/tray | Exclusive runtime state + probe `/api/runtime`; lần sau chỉ mở URL cũ |
| PID stale bị tái sử dụng | So khớp instance ID + endpoint trước khi kill; PID chết thì không kill |
