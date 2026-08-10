# ViTranscript Desktop — Tài liệu Kỹ thuật & Phát triển (Developer Documentation)

> **Dành cho:** Developer, Release Manager, CI/CD Maintainer.  
> **Kiến trúc:** Tauri v2 (vỏ Rust) + Python Sidecar đóng gói PyInstaller (`app.server`).  
> **Phạm vi OS:** Linux (Ubuntu 22.04 baseline), macOS (arm64/Intel), Windows x64.

---

## 1. Kiến trúc tổng quan

ViTranscript Desktop chuyển đổi ứng dụng FastAPI + HTML tĩnh thành một ứng dụng desktop native 100% offline (sau lần tải model đầu tiên), không phụ thuộc vào trình duyệt web ngoài hay dòng lệnh Terminal.

```text
┌──────────────────────────────────────────────────────────────────┐
│ Tauri Shell (Rust — desktop/src-tauri)                           │
│  • Spawn sidecar process (--port 0 --no-browser)                 │
│  • Đọc dòng READY từ stdout (VITRANSCRIPT_READY http://127...)   │
│  • Poll GET /healthz kiểm tra readiness                           │
│  • Khởi tạo WebView Window (1100x760) trỏ tới URL loopback        │
│  • Quản lý Native File Dialog, File Drop, Native Menu             │
│  • Lifecycle & Shutdown: gửi POST /api/shutdown + Fallback Kill  │
└────────────────────────────────────────┬─────────────────────────┘
                                         │ Loopback HTTP (127.0.0.1:<port>)
                                         │ Header: X-ViTranscript-Token
┌────────────────────────────────────────▼─────────────────────────┐
│ Python Sidecar = PyInstaller Executable (app.server)             │
│  • FastAPI + static HTML UI (chạy trên Uvicorn)                   │
│  • --port + dynamic socket bind (8756..8805)                      │
│  • FastAPI endpoints: GET /healthz, POST /api/jobs/local          │
│  • ML Runtimes: ctranslate2, onnxruntime, sherpa-onnx, av         │
│  • Bundled ffmpeg & ffprobe executable                            │
└──────────────────────────────────────────────────────────────────┘
```

### 1.1 Vòng đời & Readiness Handshake

1. **Khởi chạy Sidecar:** Rust shell spawn Python sidecar binary kèm tham số `--port 0 --no-browser` và truyền một token ngẫu nhiên 256-bit qua biến môi trường `VITRANSCRIPT_INSTANCE_TOKEN`.
2. **Dynamic Port Binding:** Sidecar tự tìm và bind trực tiếp vào port rảnh trong dải `8756..8805` (sử dụng `bind_server_socket` để tránh lỗi race condition TOCTOU).
3. **READY Signal:** Ngay khi Uvicorn hoàn tất khởi động (`started == True`), sidecar in ra stdout đúng một dòng theo format:
   `VITRANSCRIPT_READY http://127.0.0.1:<port>`
4. **Tauri Verification:** Rust shell đọc stdout sidecar với deadline 60 giây (dành cho cold extraction của PyInstaller onefile). Khi bắt được dòng READY, Rust poll `GET /healthz` mỗi 100 ms (timeout 500 ms) cho đến khi nhận `200 OK` với `{"status": "ok", "port": <port>}`.
5. **Hiển thị cửa sổ:** Sau khi verification thành công, Rust shell mới tạo và hiển thị cửa sổ WebView trỏ chính xác đến URL `http://127.0.0.1:<port>`.
6. **Thoát & Dọn dẹp Process:**
   - Nghe sự kiện đóng cửa sổ hoặc menu `File > Thoát`.
   - Gửi yêu cầu HTTP `POST /api/shutdown` với header `X-ViTranscript-Token`. Sidecar trả lời HTTP `202 Accepted` và đặt `uvicorn.Server.should_exit = True`.
   - Fallback dọn dẹp: Nếu sidecar không thoát trong vòng 5 giây, Tauri áp dụng cơ chế diệt process tree:
     - **Unix:** Tạo Unix Process Group riêng (`process_group(0)`) và gửi signal `SIGTERM` (chờ 2s), sau đó `SIGKILL` toàn bộ group.
     - **Windows:** Gán process con vào Windows Job Object có thuộc tính `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.

---

## 2. Hợp đồng Giao tiếp (Contracts)

### 2.1 Sidecar CLI Arguments

```bash
vitranscript-sidecar [--port <0..65535>] [--no-browser] [--self-test-native]
```

- `--port`: Port cố định (ví dụ: `8756`). Nếu truyền `0` hoặc bỏ trống: tự động chọn port rảnh trong dải `8756..8805`.
- `--no-browser`: Bỏ qua logic tự động mở trình duyệt hệ thống.
- `--self-test-native`: Chế độ tự kiểm tra: import tất cả 7 package native ML + chạy `ffmpeg -version` & `ffprobe -version`, in kết quả ra stdout rồi thoát với mã `0` (hoặc `1` nếu thiếu dependency).

### 2.2 Biến Môi trường (Environment Variables)

- `VITRANSCRIPT_INSTANCE_TOKEN`: Token ngẫu nhiên 256-bit do Tauri tạo ra bằng OS RNG per-instance. Dùng để xác minh tất cả request giao tiếp giữa Rust và Sidecar.
- `VITRANSCRIPT_DESKTOP`: Luôn được set thành `1` khi ứng dụng chạy ở chế độ Desktop.
- `VITRANSCRIPT_ENABLE_TEST_MODEL`: Set thành `1` trong môi trường test/CI để đăng ký key model `tiny-test` (dùng model `tiny` để test E2E nhanh mà không tốn dung lượng).

### 2.3 Endpoints API quan trọng

#### 1. Readiness Health Check
- **`GET /healthz`**
- **Response (200 OK):** `{"status": "ok", "port": 8756}`

#### 2. Local Job Execution (Desktop File Picker / Drag-Drop)
- **`POST /api/jobs/local`**
- **Headers bắt buộc:** `X-ViTranscript-Token: <token>`
- **Yêu cầu kết nối:** Chỉ chấp nhận request kết nối từ IP Loopback (`127.0.0.1` hoặc `::1`).
- **Body JSON:**
  ```json
  {
    "path": "/absolute/path/to/audio.mp3",
    "model": "phowhisper-small",
    "language": "vi",
    "diarize": true,
    "punctuate": true,
    "num_speakers": 0,
    "glossary": ""
  }
  ```
- **Quy trình Kiểm tra Bảo mật Đường dẫn (Path Validation Pipeline):**
  1. Yêu cầu `path` phải là chuỗi đường dẫn tuyệt đối (`is_absolute()`), không chứa ký tự NUL (`\x00`).
  2. Từ chối mọi component chứa relative traversal `..`.
  3. Duyệt từng cấp thư mục từ root đến file (`lstat`): từ chối nếu có bất kỳ **Symlink** nào. Trên Windows, từ chối thêm các thư mục/file dạng **Reparse Point** (Junction Point).
  4. Thực hiện `resolve(strict=True)` và kiểm tra `stat.S_ISREG` (chỉ chấp nhận regular file, từ chối Directory, FIFO, Socket, Device).
  5. Đuôi file (`suffix`) phải thuộc danh sách hỗ trợ trong `app.media` (`AUDIO_EXTS` | `VIDEO_EXTS`).
  6. **Grant-set Validation:** Phía Rust shell duy trì một danh sách Memory Grant-set các file đường dẫn do người dùng chọn trực tiếp từ Native File Picker hoặc Native Drag-Drop. Rust reject ngay nếu JS Webview gửi `path` không nằm trong Grant-set.

#### 3. Graceful Shutdown
- **`POST /api/shutdown`**
- **Headers bắt buộc:** `X-ViTranscript-Token: <token>`
- **Yêu cầu kết nối:** Loopback-only.
- **Response:** `202 Accepted` (Sidecar khởi chạy background task ngắt Uvicorn server).

---

## 3. Yêu cầu Môi trường & Prereqs Build theo OS

### 3.1 Linux (Ubuntu Baseline)

> [!CRITICAL]
> **QUY TẮC BASELINE BUILD RELEASE LINUX:**  
> Bản build phát hành (Release Artifact) dành cho Linux **BẮT BUỘC PHẢI BUILD TRÊN UBUNTU 22.04** (Baseline `glibc 2.35`).  
> Nếu build trên Ubuntu mới hơn (như 24.04 hay 26.04 có `glibc 2.38+`), file thực thi PyInstaller sẽ bị lỗi `GLIBC_2.38 not found` khi chạy trên hệ điều hành Ubuntu 22.04 LTS.  
> Các host Ubuntu mới hơn (Ubuntu 24.04/26.04) chỉ được sử dụng cho mục đích kiểm thử compatibility smoke.

**Các gói thư viện hệ thống cần cài đặt (Ubuntu 22.04):**

```bash
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev pkg-config

# Các gói dùng cho E2E / Smoke test (Headless GUI & Audio generation):
sudo apt-get install -y xvfb xdotool espeak-ng
```

**Công cụ phát triển:**
- Python 3.12 (khuyên dùng qua `uv`).
- Rust Toolchain Stable (`rustc`, `cargo`).
- Tauri CLI 2.11.4: `cargo install tauri-cli --version 2.11.4 --locked`.

### 3.2 macOS (Apple Silicon arm64 & Intel x86_64)

- macOS 13+ (Khuyên dùng macOS 15 Sonoma/Sequoia SDK).
- Xcode Command Line Tools (`xcode-select --install`).
- Python 3.12 & `uv`.
- Rust Toolchain Stable với target triples:
  - `aarch64-apple-darwin` (cho Apple Silicon M1/M2/M3/M4).
  - `x86_64-apple-darwin` (cho Mac Intel).
- Tauri CLI 2.11.4: `cargo install tauri-cli --version 2.11.4 --locked`.

### 3.3 Windows (x64)

- Windows 10/11 x64 hoặc Windows Server 2022.
- Visual Studio 2022 Build Tools (tích hợp C++ build tools workload).
- Python 3.12 & `uv`.
- Rust Toolchain Stable (`x86_64-pc-windows-msvc`).
- Tauri CLI 2.11.4.
- PowerShell 7+.

---

## 4. PyInstaller Sidecar & Bundling ffmpeg

### 4.1 PyInstaller Configuration (`vitranscript-sidecar.spec`)

Sidecar Python được đóng gói bằng PyInstaller theo 2 mode:
1. **`onedir` (Diagnostic Mode):** Dùng để phân tích thư mục `_internal`, kiểm tra các file `.so`/`.dylib`/`.dll` native libs và chạy thử nghiệm import probe.
2. **`onefile` (Release Mode):** Chế độ chính thức dùng làm Tauri `externalBin`.

**Cấu hình Collect Native Libraries:**  
Tệp spec sử dụng `collect_all()` cho 7 gói native bắt buộc:
- `ctranslate2`, `onnxruntime`, `sherpa_onnx`, `tokenizers`, `faster_whisper`, `av`, `static_ffmpeg`.

**Xử lý đặc biệt cho `sherpa-onnx-core`:**  
Spec tự động đọc distribution metadata của `sherpa-onnx-core`, đưa toàn bộ file `.so`, `.dylib`, `.dll`, `.pyd` vào danh sách `binaries` và giữ nguyên relative parent structure.

> [!IMPORTANT]
> PyInstaller spec tuyệt đối **KHÔNG** collect `torch` hoặc `tensorflow`. Mọi phụ thuộc ML trong dự án đều chạy trên CTranslate2 và ONNX Runtime INT8 để đảm bảo dung lượng nhẹ và không bị dính PyTorch framework.

### 4.2 Tích hợp & Kiểm duyệt Giấy phép ffmpeg (ffmpeg License Audit)

Để ứng dụng hoàn toàn tự chủ mà không bắt người dùng cài đặt `ffmpeg`, build script tự động download và bundle hai file thực thi `ffmpeg` và `ffprobe` vào trong sidecar.

- **Resolver Script:** `desktop/scripts/ffmpeg_license_audit.py`.
- **Cơ chế:**
  1. Kiểm tra ưu tiên các bản build **NONFREE** / **GPL** / **LGPL** chính thức.
  2. Thực hiện trích xuất `ffmpeg -version` để lấy thông tin version line và configuration flags.
  3. Ghi manifest chẩn đoán tại `desktop/pyinstaller/dist/sidecar-manifest.json` và tạo thư mục `ffmpeg-notices/` chứa `SOURCE_OFFER.txt` cùng giấy phép bản quyền tương ứng.
  4. Hai file `ffmpeg` và `ffprobe` được bundle trực tiếp vào thư mục `binaries` cấp phát của sidecar.
  5. Khi runtime có `sys.frozen`, module `app.media` sẽ ưu tiên sử dụng cặp `ffmpeg/ffprobe` đã đóng gói này.

### 4.3 Kịch bản Build (Build Scripts)

- **Tạo Python Sidecar:**
  - Linux/macOS: `bash desktop/scripts/build-sidecar.sh`
  - Windows: `.\desktop\scripts\build-sidecar.ps1`
- **Build Đầy đủ Ứng dụng Desktop (PyInstaller + Tauri):**
  - Linux: `bash desktop/scripts/build-linux.sh`
  - macOS: `bash desktop/scripts/build-macos.sh`
  - Windows: `.\desktop\scripts\build-windows.ps1`

**Target Triple Naming Rules:**  
Tauri v2 yêu cầu file sidecar trong `desktop/src-tauri/binaries/` phải tuân theo đúng đặt tên target triple của host build:
- Linux x64: `vitranscript-sidecar-x86_64-unknown-linux-gnu`
- macOS arm64: `vitranscript-sidecar-aarch64-apple-darwin`
- macOS Intel: `vitranscript-sidecar-x86_64-apple-darwin`
- Windows x64: `vitranscript-sidecar-x86_64-pc-windows-msvc.exe`

---

## 5. Cấu trúc Thư mục `desktop/`

```text
desktop/
├── frontend/
│   └── index.html                # HTML placeholder tối thiểu cho Tauri bundle config
├── icons/                        # Icon gốc 1024x1024 PNG & các định dạng icon (.ico, .icns)
├── pyinstaller/
│   ├── sidecar_entry.py          # Entrypoint gọi app.server.main()
│   ├── vitranscript-sidecar.spec # Cấu hình PyInstaller spec
│   ├── _ffmpeg_resolve.json      # File cache thông tin ffmpeg binary đã download
│   └── dist/                     # Thư mục chứa sidecar binary & manifest sau khi build
├── scripts/
│   ├── build-sidecar.sh / .ps1   # Script build PyInstaller sidecar
│   ├── build-linux.sh            # Script build toàn bộ artifact cho Linux (.AppImage, .deb)
│   ├── build-macos.sh            # Script build toàn bộ artifact cho macOS (.dmg, .app)
│   ├── build-windows.ps1         # Script build toàn bộ artifact cho Windows (.exe, NSIS)
│   └── ffmpeg_license_audit.py   # Tool audit giấy phép & download ffmpeg
└── src-tauri/                    # Mã nguồn Tauri v2 (Rust Shell)
    ├── Cargo.toml / Cargo.lock   # Dependencies Rust
    ├── tauri.conf.json           # Cấu hình chung Tauri
    ├── tauri.linux.conf.json     # Cấu hình bundle cho Linux (appimage, deb)
    ├── tauri.macos.conf.json     # Cấu hình bundle cho macOS (dmg)
    ├── tauri.windows.conf.json   # Cấu hình bundle cho Windows (nsis)
    ├── capabilities/             # Cấu hình phân quyền Tauri Remote Capabilities
    └── src/
        ├── main.rs               # Main entry point & Tauri App initialization
        ├── sidecar.rs            # Quản lý spawn, handshake, log drain & kill process group/Job Object
        ├── native.rs             # Bridge Native File Picker, Native Drag-Drop & Grant-set
        └── job_options.rs        # Mapping Struct dữ liệu tham số job
```

---

## 6. CI/CD Matrix Pipeline (`.github/workflows/desktop-build.yml`)

Quy trình CI tự động hóa việc build và kiểm thử trên 4 môi trường runner:

| Job Name | Runner OS | Target Triple | Artifacts Sinh ra |
|---|---|---|---|
| `linux` | `ubuntu-22.04` | `x86_64-unknown-linux-gnu` | `.AppImage`, `.deb`, `sidecar-manifest.json` |
| `macos-arm64` | `macos-15` | `aarch64-apple-darwin` | `.dmg`, `.app`, `sidecar-manifest.json` |
| `macos-intel` | `macos-15-intel` | `x86_64-apple-darwin` | `.dmg`, `.app`, `sidecar-manifest.json` |
| `windows` | `windows-2022` | `x86_64-pc-windows-msvc` | NSIS `.exe` Installer, `sidecar-manifest.json` |

### Quy trình kiểm thử trong CI:
1. **Python Unit Tests:** Chạy `uv run pytest tests/ -v` kiểm tra core logic.
2. **Rust Library Unit Tests:** Chạy `cargo test --manifest-path desktop/src-tauri/Cargo.toml --lib` (kiểm tra readiness parser, deadline, health validator, shutdown state mà không cần hiển thị GUI).
3. **Sidecar E2E Online & Offline (Ubuntu):**
   - Đóng gói onefile sidecar.
   - Chạy `scripts/e2e_sidecar_linux.py` chế độ Online: Tải model `tiny-test` vào thư mục cache `XDG_DATA_HOME`.
   - Chạy lại chế độ Offline sử dụng `docker run --network none` (hoặc `unshare -n`) tái sử dụng đúng cache `XDG_DATA_HOME`. Đảm bảo pipeline hoàn tất 100% và tạo file export.
4. **Tauri Headless Xvfb Smoke:** Chạy `scripts/smoke_desktop_linux.sh` dưới `xvfb-run` để verify quá trình khởi tạo cửa sổ và bắt dòng READY.

---

## 7. Chẩn đoán & Sửa lỗi Kỹ thuật (Troubleshooting & Debugging)

### 7.1 Kiểm tra Log ứng dụng

File log của Sidecar và Tauri Shell được ghi trực tiếp tại thư mục data chuẩn của OS:
- **Linux:** `~/.local/share/ViTranscript/logs/` (hoặc `$XDG_DATA_HOME/ViTranscript/logs/`)
- **macOS:** `~/Library/Application Support/ViTranscript/logs/`
- **Windows:** `%APPDATA%\ViTranscript\logs\`

### 7.2 Lỗi Handshake / Timeout 60 giây khi Khởi động App

- **Triệu chứng:** Xuất hiện Hộp thoại thông báo lỗi tiếng Việt khi khởi động app: `"Không thể khởi động dịch vụ nhận dạng (Timeout/Sidecar exited)"`.
- **Nguyên nhân thường gặp:**
  1. Lần đầu giải nén PyInstaller `onefile` trên đĩa cứng đĩa HDD chậm vượt quá 60 giây.
  2. Port trong dải `8756..8805` bị tường lửa hoặc phần mềm diệtไวรัส (Antivirus) chặn loopback bind.
- **Cách khắc phục & Debug:**
  - Chạy thử sidecar trực tiếp từ Terminal để xem log stdout:
    ```bash
    ./desktop/pyinstaller/dist/vitranscript-sidecar --self-test-native
    ./desktop/pyinstaller/dist/vitranscript-sidecar --port 8756 --no-browser
    ```
  - Kiểm tra xem dòng `VITRANSCRIPT_READY http://127.0.0.1:8756` có xuất hiện hay không.

### 7.3 Bảng Trạng thái Nghiệm thu Thực tế hiện tại (Status Report)

| Thành phần | Trạng thái thực tế | Ghi chú kỹ thuật |
|---|---|---|
| Sidecar E2E Ubuntu 22.04 (Online + Offline) | 🟢 **PASS** | Chạy thành công trên container clean Ubuntu 22.04 baseline. |
| Core Python Tests & Rust Lib Tests | 🟢 **PASS** | 127 Python tests pass; 14 Rust lib unit tests pass. |
| Tauri GUI Xvfb Smoke (Headless Linux) | 🔵 **BLOCKED(env)** | Môi trường dev hiện tại thiếu thư viện hệ thống `libwebkit2gtk-4.1-dev` và `pkg-config` (sẽ PASS trên CI `ubuntu-22.04`). |
| macOS Native Verification | 🔵 **CHỜ VERIFY MÁY THẬT** | Cấu hình CI `macos-15` & `macos-15-intel` đã sẵn sàng, chờ kiểm thử trực tiếp trên máy Mac thật. |
| Windows Native Verification | 🔵 **CHỜ VERIFY MÁY THẬT** | Script `build-windows.ps1` & CI `windows-2022` đã có, chờ nghiệm thu Job Object trên máy Windows thật. |
