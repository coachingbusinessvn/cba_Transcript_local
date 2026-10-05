# Spec: Desktop Shell v1.5 cho ViTranscript

> **Trạng thái:** đã chốt về thiết kế, sẵn sàng lập trình; **chưa triển khai**.
> **Ngày chốt:** 2026-07-19.
> **Plan thực thi:** [dev/plans/2026-07-19-desktop-shell.md](dev/plans/2026-07-19-desktop-shell.md).
> **Theo dõi:** [10-tasks-desktop-shell.md](10-tasks-desktop-shell.md).

## 1. Mục tiêu

Biến bản ViTranscript hiện có thành trải nghiệm desktop một chạm cho người dùng không
rành kỹ thuật trên macOS và Windows:

- cài lần đầu bằng double-click;
- dùng hằng ngày bằng icon app/shortcut, không hiện Terminal hay console;
- giao diện vẫn là web UI local trong browser;
- có tray/menu-bar để mở lại giao diện và thoát app;
- gỡ sạch app, môi trường Python và model theo xác nhận rõ ràng;
- giữ nguyên toàn bộ ràng buộc core v1.

Tên “v1.5” là tên **milestone sản phẩm**, không tự động đổi version trong
`pyproject.toml`, không tự động tạo tag và không đồng nghĩa với SemVer `1.5.0`.

## 2. Người dùng và trải nghiệm đích

### 2.1 Cài lần đầu

1. Tải ZIP và giải nén vào một thư mục cố định.
2. Double-click `install.command` trên macOS hoặc `install.bat` trên Windows.
3. Vượt Gatekeeper/SmartScreen một lần theo hướng dẫn có ảnh.
4. Installer tự cài `uv`, Python 3.12 và dependencies; cần mạng ở bước này.
5. Kết thúc với `ViTranscript.app` trong Applications hoặc shortcut trên Desktop và
   Start Menu.

Thư mục đã giải nén là **thư mục cài đặt** và phải được giữ nguyên khi còn dùng app,
vì `.venv` và code runtime nằm tại đó. Installer và README phải nói rõ điều này.

### 2.2 Dùng hằng ngày

1. Mở icon app/shortcut.
2. Không xuất hiện Terminal/console.
3. Server chỉ bind `127.0.0.1`, chọn port trống trong dải `8756..8805`.
4. Browser mở UI sau khi server thực sự sẵn sàng.
5. Đóng tab không dừng app; menu `Mở giao diện` mở lại đúng instance hiện tại.
6. Menu `Thoát` dừng uvicorn và process thật, xóa runtime state.

Nếu người dùng double-click icon khi ViTranscript đã chạy, app **không tạo process
server thứ hai**. Lần mở mới chỉ mở browser tới instance đang chạy rồi tự kết thúc.

### 2.3 Gỡ cài đặt

1. Double-click `uninstall.command` hoặc `uninstall.bat`.
2. Script in dung lượng data/model sắp xóa.
3. Xác nhận thứ nhất xóa app/shortcut, data/model và `.venv`.
4. Xác nhận thứ hai là tùy chọn, mặc định **không**, để xóa `uv` và Python do `uv`
   quản lý. Prompt phải cảnh báo đây có thể là công cụ dùng chung.
5. Thư mục source chứa script không tự xóa; người dùng kéo nó vào Trash/Recycle Bin
   sau khi script kết thúc.

## 3. Quyết định kiến trúc đã chốt

| Chủ đề | Quyết định |
|---|---|
| UI | Giữ FastAPI + một trang HTML mở trong browser |
| Native window | Không dùng `pywebview`, Electron hay cửa sổ native |
| Packaging | Không dùng PyInstaller, DMG, Inno Setup |
| Runtime | Python 3.12 do `uv` quản lý; daily launcher chạy Python trong `.venv` bằng đường dẫn tuyệt đối |
| Tray | `pystray` + Pillow; đúng hai menu `Mở giao diện`, `Thoát` |
| Server | `uvicorn.Server`; uvicorn ở thread phụ, tray ở main thread trên macOS/Windows |
| Network | Chỉ `127.0.0.1`; không bind `0.0.0.0`; không thêm remote API |
| Đồng thời | Một server instance/user profile và một transcription job tại một thời điểm |
| Ký số | Chưa ký/notarize; hướng dẫn Gatekeeper/SmartScreen bằng ảnh |
| Auto-update | Không có; cập nhật bằng ZIP mới rồi chạy lại installer |
| Gỡ cài đặt | Hai xác nhận; chỉ xóa target đã xác định và kiểm tra |

Không được thêm dependency kéo theo PyTorch hoặc TensorFlow. URL upstream có typo
`speaker-recongition-models` phải giữ nguyên nếu file liên quan được chạm tới.

## 4. Thành phần và trách nhiệm

### 4.1 `app/server.py`

- giữ nguyên HTTP endpoints và khóa một-job;
- chọn port local;
- claim một runtime state duy nhất;
- khởi động `uvicorn.Server` ở thread phụ khi bật tray;
- chỉ mở browser sau khi `uvicorn_server.started` là true;
- dừng server có kiểm soát khi tray yêu cầu;
- xóa runtime state trong `finally` chỉ khi state thuộc đúng instance hiện tại;
- hỗ trợ `VITRANSCRIPT_NO_TRAY=1` cho test/headless/debug.

### 4.2 `app/runtime.py`

Module riêng quản lý single-instance và runtime state, để `server.py` không chứa logic
filesystem/process quá lớn.

State đặt tại `<data_dir>/server-state.json` với schema:

```json
{
  "schema_version": 1,
  "app": "ViTranscript",
  "instance_id": "uuid-hex",
  "pid": 12345,
  "port": 8756,
  "install_dir": "/absolute/path/to/install",
  "started_at": "2026-07-19T10:00:00+07:00"
}
```

Yêu cầu:

- tạo state bằng exclusive create để hai lần double-click đồng thời không cùng claim;
- state hợp lệ phải có app, instance ID, PID số dương, port trong `8756..8805`;
- instance mới probe `GET /api/runtime` tối đa 3 giây;
- nếu endpoint trả cùng `instance_id` và PID, mở URL cũ và thoát mã 0;
- chỉ coi state là stale khi process không tồn tại hoặc endpoint không khớp sau thời
  gian chờ; khi đó xóa state bằng so sánh instance ID rồi claim lại;
- cleanup không được xóa state của instance khác.

Endpoint `GET /api/runtime` trả đúng các field nhận diện `app`, `instance_id`, `pid`
và `port`; không trả đường dẫn cài đặt hay dữ liệu người dùng.

### 4.3 `app/tray.py`

- không import backend GUI ở module import time; lazy-import `pystray` trong
  `create_icon()` để test/headless vẫn import app được;
- tải `assets/icon.png`, có fallback icon tạo bằng Pillow;
- menu đúng hai mục tiếng Việt;
- callback `Mở giao diện` dùng URL `http://127.0.0.1:<port>`;
- callback `Thoát` yêu cầu uvicorn shutdown rồi dừng icon;
- `pystray.Icon.run()` chạy ở main thread.

### 4.4 Logging

- log ứng dụng: `<data_dir>/logs/server.log`;
- lỗi trước khi Python logging sẵn sàng trên macOS:
  `<data_dir>/logs/launcher.log`; trên Windows, VBS phải hiện dialog rõ ràng nếu
  interpreter/runtime bị thiếu, còn lỗi sau import ghi vào `server.log`;
- handler file phải idempotent, không nhân đôi log khi test/import lại;
- không log transcript, glossary, nội dung file hoặc token nhạy cảm;
- log tối thiểu: thời điểm start/stop, port, lỗi startup, job ID/stage và traceback lỗi.

## 5. Hợp đồng nền tảng

### 5.1 macOS

`install.command`:

- dùng `set -euo pipefail` và resolve thư mục cài tuyệt đối;
- cài/tìm `uv` bằng đường dẫn tuyệt đối, chạy `uv python install 3.12` và `uv sync`;
- sinh `/Applications/ViTranscript.app/Contents/{MacOS,Resources}`;
- `Info.plist` có bundle id `com.vitranscript.app`, executable `launcher`, icon
  `icon.icns`, `LSUIElement=true`;
- launcher dùng `<install_dir>/.venv/bin/python -m app.server`, không phụ thuộc PATH;
- stdout/stderr bootstrap append vào `launcher.log`;
- chỉ thay đúng `/Applications/ViTranscript.app`, không xóa target rộng hơn;
- chạy lại installer là idempotent và không xóa model/settings/jobs.

`assets/icon.icns` được tạo bằng iconset chuẩn gồm 16, 32, 128, 256, 512 và các bản
`@2x`, không dùng danh sách filename tùy ý mà `iconutil` không nhận.

### 5.2 Windows

`install.bat` phải ASCII-only:

- resolve `%~dp0`, cài/tìm `uv`, cài Python 3.12, chạy `uv sync`;
- kiểm tra `.venv\Scripts\pythonw.exe` và `assets\icon.ico`;
- gọi PowerShell tạo đúng hai shortcut: Desktop và Start Menu;
- không tự chạy `run.bat` sau cài.

Shortcut chính gọi `wscript.exe //nologo scripts\launch-hidden.vbs`; VBS đặt working
directory về thư mục cài rồi chạy `.venv\Scripts\pythonw.exe -m app.server` ẩn.

Fallback khi antivirus chặn VBS: shortcut trỏ trực tiếp tới
`.venv\Scripts\pythonw.exe`, arguments `-m app.server`, working directory là thư mục
cài. README phải ghi chính xác ba trường này.

## 6. Uninstall an toàn

### 6.1 Target được phép xóa

| Nền tảng | Xác nhận 1 | Xác nhận 2, tùy chọn |
|---|---|---|
| macOS | `<data_dir>`, `/Applications/ViTranscript.app`, `<install_dir>/.venv` | executable `uv`, `uvx` và thư mục Python/cache do `uv` báo về |
| Windows | `%APPDATA%\ViTranscript`, hai shortcut chính xác, `<install_dir>\.venv` | executable `uv`, `uvx` và thư mục Python do `uv python dir` xác nhận |

### 6.2 Điều kiện an toàn bắt buộc

- Không dùng `pkill -f`, không kill theo tên process và không dùng wildcard target.
- Nếu PID trong state không còn tồn tại, coi state là stale và tiếp tục mà không kill.
  Nếu PID còn tồn tại, chỉ dừng khi `GET /api/runtime` trả cùng app, `instance_id`, PID
  và port. Nếu PID sống nhưng không xác minh được, yêu cầu người dùng thoát từ tray rồi
  chạy lại uninstaller; không kill PID mù.
- Mọi đường dẫn phải absolute, non-empty, có basename/parent đúng hợp đồng.
- Không xóa `/`, home directory, `%USERPROFILE%`, `%APPDATA%` hoặc parent của target.
- Câu trả lời khác `y`/`Y` được hiểu là không.
- Nhánh trả lời `N` không được làm thay đổi filesystem.
- Thu thập đường dẫn `uv python dir` trước khi xóa executable `uv`; nếu không xác minh
  được thì giữ lại và in hướng dẫn, không suy đoán.
- Test destructive chỉ chạy với HOME/user profile giả trong temp hoặc VM snapshot.

## 7. Cập nhật và cài lại

- Chạy installer từ ZIP mới cập nhật dependencies, launcher, bundle/shortcut và icon.
- Không xóa data/model/settings/glossary/jobs khi cập nhật.
- Nếu app đang chạy, installer phải yêu cầu thoát từ tray trước khi thay launcher;
  không thay runtime giữa một job đang chạy.
- Sau uninstall xác nhận 1, cài lại ngay phải tạo được môi trường sạch.
- Sau uninstall xác nhận 2, cài lại phải tự cài lại `uv` và Python.

## 8. Bảo mật và riêng tư

- Toàn bộ transcript vẫn xử lý local; desktop shell không thêm upload/telemetry.
- Server chỉ listen loopback IPv4 `127.0.0.1`.
- Không bật CORS rộng, không thêm endpoint shutdown công khai.
- Runtime endpoint chỉ cung cấp metadata nhận diện process, không chứa path hoặc nội
  dung người dùng.
- Script không dùng `eval`, không nội suy đường dẫn chưa quote, không phụ thuộc PATH
  ở daily runtime.
- Bundle/shortcut chưa ký phải được mô tả trung thực; không hướng dẫn tắt cơ chế bảo
  vệ toàn hệ thống.

## 9. Khả năng tương thích

- Python: `>=3.10,<3.13`, installer chọn 3.12.
- macOS: máy Intel hoặc Apple Silicon còn chạy được Python 3.12 và dependencies hiện tại.
- Windows: Windows 10/11 x64, PowerShell 5.1+, WSH được bật.
- Linux: server/headless vẫn chạy với `VITRANSCRIPT_NO_TRAY=1`; desktop shell Linux
  nằm ngoài phạm vi nghiệm thu.
- Windows ARM và môi trường chặn WSH/VBS không phải luồng chính; direct `pythonw.exe`
  là fallback được hỗ trợ.

## 10. Ma trận nghiệm thu

| ID | Tiêu chí | Nền tảng | Bằng chứng bắt buộc |
|---|---|---|---|
| DS-01 | Installer chạy bằng double-click và hoàn tất | Mac + Windows | quay/chụp luồng thật, exit thành công |
| DS-02 | Bundle/shortcut được tạo đúng vị trí và icon | Mac + Windows | kiểm tra artifact thật |
| DS-03 | Daily launch không hiện Terminal/console | Mac + Windows | quan sát trên máy thật |
| DS-04 | Server chỉ bind `127.0.0.1` | Tự động + thật | test config và kiểm tra socket/log |
| DS-05 | Browser chỉ mở sau khi server sẵn sàng | Mac + Windows | mở lần đầu không connection-refused |
| DS-06 | Double-click lần hai mở instance cũ, không tạo server thứ hai | Mac + Windows | PID/port không đổi |
| DS-07 | Tray đúng hai mục và mở lại UI sau khi đóng tab | Mac + Windows | thao tác tay |
| DS-08 | `Thoát` dừng process và xóa state | Mac + Windows | PID biến mất, state không còn |
| DS-09 | HTTP 409 một-job và core smoke không regression | Tự động + Mac | pytest + smoke E2E |
| DS-10 | Log được ghi vào data dir, không ghi transcript | Tự động | test path + kiểm tra log |
| DS-11 | Xác nhận uninstall 1 = N không xóa gì | Mac + Windows | fixture temp/VM |
| DS-12 | Xác nhận uninstall 1 = Y xóa app/shortcut, data/model, `.venv` | Mac + Windows | fixture + máy thật |
| DS-13 | Xác nhận uninstall 2 mặc định giữ `uv`; Y chỉ xóa target đã xác minh | Mac + Windows | fixture + log target |
| DS-14 | Cài lại ngay sau uninstall hoạt động | Mac + Windows | luồng thật |
| DS-15 | `.bat` ASCII-only; dependency tree không có torch/tensorflow | Tự động | byte scan + `uv tree` |
| DS-16 | Gatekeeper/SmartScreen và fallback VBS có hướng dẫn ảnh | Docs | review README trên máy thật |

Không được ghi PASS cho Mac dựa trên unit test, hoặc PASS cho Windows dựa trên kiểm
tra tĩnh từ macOS. Windows bắt buộc có bằng chứng từ máy Windows thật/VM tương đương.

## 11. Out of scope

- ký số, notarization, chứng chỉ SmartScreen;
- DMG/MSI/Inno Setup/PyInstaller;
- auto-update và rollback phiên bản;
- native window;
- Linux desktop integration;
- service chạy lúc login;
- nhiều server instance hoặc nhiều job song song;
- tự xóa source folder chứa uninstaller.

## 12. Rủi ro còn mở

| Rủi ro | Cách kiểm soát / điều kiện đóng |
|---|---|
| `pystray`/AppKit yêu cầu main thread | Test tray thật trên macOS; uvicorn chạy thread phụ |
| Windows antivirus chặn VBS | Verify direct `pythonw.exe` fallback và ghi README |
| Source folder bị di chuyển sau cài | Installer + README cảnh báo; launcher log chỉ rõ path bị thiếu |
| PID bị tái sử dụng | Runtime state có instance ID + probe endpoint trước khi kill |
| App chết để lại state stale | Test stale recovery và exclusive claim |
| Launcher lỗi trước khi logging khởi tạo | Mac ghi `launcher.log`; Windows VBS preflight và hiện dialog nếu runtime thiếu |
| macOS/Windows thay đổi cảnh báo unsigned | Ảnh hướng dẫn gắn OS version và được cập nhật khi nghiệm thu |
| Optional xóa `uv` ảnh hưởng project khác | Prompt 2 cảnh báo shared tool, mặc định N, chỉ xóa path đã xác minh |

## 13. Traceability tới plan

| Nhóm yêu cầu | Task trong plan |
|---|---|
| Runtime state, single-instance, logging, tray, shutdown | Task 1 |
| Icon và macOS app bundle | Task 2 |
| Windows hidden launch và shortcuts | Task 3 |
| Uninstall hai xác nhận và safety fixture | Task 4 |
| README, ảnh cảnh báo, diagnostics | Task 5 |
| Ma trận DS-01..DS-16 và cập nhật trạng thái | Task 6 |
