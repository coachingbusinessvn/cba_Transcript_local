# Spec: ViTranscript Desktop (Tauri + Python sidecar)

> **Ngày chốt:** 2026-08-10. **Trạng thái:** đã chốt với người dùng và finalize sau
> technical review. Kiến trúc Tauri + PyInstaller sidecar không đổi; review chỉ khóa chi
> tiết package/lifecycle/security và bỏ tray khỏi v1 desktop vì close window = thoát app.
> **Thay thế:** design này **supersede** hướng "Desktop Shell v1.5" tại
> [../09-spec-desktop-shell.md](../09-spec-desktop-shell.md) và
> [../04-desktop-design.md](../04-desktop-design.md) — bản cũ chọn browser + `pystray`,
> KHÔNG PyInstaller, KHÔNG native window, chỉ Mac/Windows và **chưa từng được triển khai**.
> Người dùng đã đổi hướng: dùng **Tauri (vỏ Rust) + Python sidecar đóng gói PyInstaller**,
> cửa sổ native, installer đầy đủ cho **macOS, Windows và Ubuntu**.

## 1. Mục tiêu

Biến ViTranscript (FastAPI + 1 trang HTML tĩnh) thành ứng dụng desktop thật cho người
dùng không rành kỹ thuật trên **macOS (arm64 + x86_64), Windows x64, Ubuntu**:

- chạy trong **cửa sổ native** (Tauri webview), không mở browser ngoài, không Terminal;
- phân phối bằng **installer/binary native** double-click: macOS `.app`/`.dmg`,
  Windows `.exe`/NSIS, Ubuntu `.AppImage` + `.deb`;
- có **menu bar native**, **hộp thoại chọn file native**, **kéo-thả file**;
- model vẫn **tải lần đầu** từ HuggingFace về data dir (installer nhỏ), sau đó offline;
- giữ nguyên toàn bộ ràng buộc core v1 (loopback-only, 1 job, không PyTorch/TensorFlow).

## 2. Kiến trúc

```
┌─────────────────────────────────────────────┐
│ Tauri shell (Rust, desktop/src-tauri)        │
│  • spawn sidecar, đọc READY, poll /healthz   │
│  • cửa sổ webview → http://127.0.0.1:<port>  │
│  • menu / dialog / drag-drop (native)         │
│  • kill sidecar khi thoát                     │
└───────────────┬─────────────────────────────┘
                │ loopback HTTP (127.0.0.1:<port>)
┌───────────────▼─────────────────────────────┐
│ Python sidecar = PyInstaller(app.server)     │
│  • FastAPI + static HTML (giữ nguyên)         │
│  • --port + fallback, /healthz, in READY      │
│  • ctranslate2 / onnxruntime / sherpa-onnx    │
│  • model tải lần đầu về data dir              │
└─────────────────────────────────────────────┘
```

### 2.1 Hợp đồng khởi động (readiness handshake)

- `python -m app.server` (và binary PyInstaller) nhận `--port <n>`; nếu 0/không cho thì
  chọn port trống trong dải `8756..8805` như hiện tại.
- Thêm endpoint `GET /healthz` → `{"status":"ok","port":<n>}` (200) dùng để poll.
- Khi uvicorn đã `started`, in đúng **một** dòng ra stdout:
  `VITRANSCRIPT_READY http://127.0.0.1:<port>`.
- Tauri: đọc stdout sidecar tới khi thấy dòng READY (deadline tổng 60 giây cho cold
  onefile extraction), rồi poll `/healthz` xác nhận trước khi tạo/hiện cửa sổ.
- Nếu sidecar chết hoặc timeout: hiện dialog lỗi tiếng Việt + đường dẫn log, thoát sạch.

### 2.2 Vòng đời & thoát

- Đóng cửa sổ hoặc chọn menu "Thoát" → Tauri gửi tín hiệu tắt sidecar (ưu tiên endpoint
  loopback shutdown có xác thực instance, fallback terminate đúng process group/Windows
  Job Object của sidecar mà Tauri đã spawn — **không** `pkill -f`, không kill theo tên).
- Chỉ một sidecar cho mỗi lần chạy app (Tauri quản PID con trực tiếp, không cần dò PID
  toàn hệ thống). Ràng buộc "1 job tại một thời điểm" của core giữ nguyên (409).

### 2.3 Đóng gói sidecar (PyInstaller) — rủi ro chính

- PyInstaller onedir dùng làm build chẩn đoán native libs; sidecar release dùng onefile
  từ cùng `Analysis` để tương thích `externalBin` một-file của Tauri. Thu thập native
  libs: `ctranslate2`, `onnxruntime`, `sherpa-onnx` + `sherpa-onnx-core`, `tokenizers`,
  `faster-whisper`, `av`, `static-ffmpeg`, đồng thời bundle `ffmpeg` + `ffprobe` cụ thể.
- Cần `--collect-all` / `hiddenimports` / `binaries` cho các gói native; giữ `app/static`
  qua `datas`.
- Binary đặt làm Tauri `externalBin` (sidecar) đúng quy ước target-triple của Tauri.
- Plan PHẢI có **spike đóng gói** trước: chứng minh binary chạy độc lập, `/healthz` OK,
  chạy được 1 job `tiny` trên máy sạch (không venv dev) trên Ubuntu.

## 3. Tính năng native (trong phạm vi vòng này)

| Tính năng | Cách làm | Ghi chú |
|---|---|---|
| Cửa sổ native | Tauri window trỏ tới URL sidecar | tiêu đề "ViTranscript", icon app |
| Menu bar | Tauri menu: File(Mở…, Thoát), Help(Giới thiệu, Tài liệu) | i18n tiếng Việt |
| Chọn file native | Tauri dialog → gửi **đường dẫn local** cho backend | không upload lại |
| Kéo-thả | Tauri file-drop event → cùng endpoint đường dẫn local | nhiều file: xử lý tuần tự (1 job) |

Không có system tray trong v1 desktop: close window là thoát app, nên tray trùng vòng đời
với menu/window và tăng khác biệt platform không cần thiết. Có thể thiết kế lại tray như
một task độc lập nếu sau này cần chạy nền.

### 3.1 Endpoint đường dẫn local (mới)

- Thêm `POST /api/jobs/local` nhận absolute `path` cùng bộ option transcript hiện có — vì
  tất cả chạy loopback trên máy người dùng, không cần re-upload file lớn.
- **Bảo mật:** chỉ chấp nhận khi peer socket là loopback và header chứa đúng token ngẫu
  nhiên per-instance do Tauri giữ; validate absolute path, reject `..`, symlink/reparse
  point ở mọi component, require regular file tồn tại và đuôi hợp lệ. Không tin proxy
  headers, không thêm CORS rộng, không endpoint remote.
- Endpoint upload multipart hiện tại giữ nguyên (fallback / tương thích UI).

## 4. Phân phối & build

| OS | Artifact | Công cụ |
|---|---|---|
| macOS arm64 + x86_64 | `.app` + `.dmg` | Tauri bundler (dmg) |
| Windows x64 | `.exe` + NSIS installer | Tauri bundler (nsis) |
| Ubuntu | `.AppImage` + `.deb` | Tauri bundler (appimage, deb) |

- Build local có script (`desktop/scripts/build-<os>.*`) + **GitHub Actions matrix**
  (`ubuntu-22.04`, `macos-15`, `macos-15-intel`, `windows-2022`) chạy PyInstaller rồi
  `tauri build` đúng native target; không cross-build sidecar.
- **Trong phiên này:** chỉ build + e2e **Ubuntu** trên máy hiện tại; Mac/Windows chỉ wire
  cấu hình CI/script, verify ở nơi khác sau.

## 5. Ký số / notarization — OUT OF SCOPE vòng này

- Artifact **chưa ký**. Docs hướng dẫn vượt Gatekeeper (macOS) và SmartScreen (Windows).
- Lối cắm tương lai: thêm bước `codesign`/`notarytool` (mac) và signtool (win) vào CI.

## 6. Ràng buộc giữ nguyên (core v1)

- `requires-python = ">=3.10,<3.13"`; KHÔNG kéo PyTorch/TensorFlow.
- Server chỉ bind `127.0.0.1`; 1 job tại một thời điểm (409 nếu đang chạy).
- Text UI tiếng Việt; `.bat`/script Windows ASCII-only (không dấu).
- Typo upstream `speaker-recongition-models` giữ nguyên nếu chạm tới file liên quan.
- Data dir theo OS: `~/Library/Application Support/ViTranscript` (mac),
  `%APPDATA%\ViTranscript` (win), `~/.local/share/ViTranscript` (linux).

## 7. Testing

- Unit tests hiện có phải xanh (`uv run pytest tests/ -v`), ruff sạch.
- Thêm test cho `--port`/`/healthz`/READY line và `POST /api/jobs/local` (headless,
  không cần Tauri).
- **E2E chỉ Ubuntu**: chạy sidecar onefile và Tauri shell đã đóng gói → cửa sổ/server lên
  → `/healthz` OK → chạy 1 job trên **audio test tự sinh** với model test `tiny` → khẳng
  định có file export.
- **Test data tự tạo:** dùng `espeak-ng` tạo speech tiếng Việt rồi ffmpeg normalize WAV;
  không dùng sine/silence đơn thuần vì export cần transcript có ít nhất một câu. Mục tiêu
  e2e là luồng end-to-end, không phải độ chính xác WER.

## 8. Ma trận nghiệm thu

| ID | Tiêu chí | Phạm vi phiên này |
|---|---|---|
| DT-01 | `app.server` hỗ trợ `--port`, `/healthz`, in READY line | Tự động (unit) |
| DT-02 | `POST /api/jobs/local` chạy pipeline, validate loopback/token/path/link/file | Tự động (unit) |
| DT-03 | Sidecar PyInstaller chạy độc lập trên máy sạch, `/healthz` OK | Ubuntu |
| DT-04 | Tauri shell spawn sidecar, đợi READY, hiện cửa sổ đúng URL | Ubuntu |
| DT-05 | Menu / dialog chọn file / kéo-thả / queue tuần tự hoạt động | Ubuntu (Mac/Win: sau) |
| DT-06 | Đóng cửa sổ/Thoát → sidecar bị tắt sạch (không process treo) | Ubuntu |
| DT-07 | `tauri build` tạo `.AppImage` + `.deb` | Ubuntu |
| DT-08 | Cấu hình build Mac (.dmg) + Windows (.exe/nsis) + CI matrix có mặt | Static/CI (verify OS thật sau) |
| DT-09 | E2E Ubuntu: launch → job trên audio tự sinh → có export | Ubuntu |
| DT-10 | Không PyTorch/TensorFlow; loopback-only; 1-job 409 giữ nguyên | Tự động |
| DT-11 | Docs dev (build/CI/packaging) + docs user (cài, vượt cảnh báo, dùng) | Docs |

> Không ghi PASS Mac/Windows dựa trên kết quả Ubuntu hoặc kiểm tra tĩnh. Các mục Mac/Win
> để "chờ verify máy thật".

## 9. Out of scope

- Ký số/notarization; auto-update; bundle model vào installer; Windows ARM; Linux distro
  ngoài Ubuntu (Fedora/Arch); đa job song song; đa instance; system tray/chạy nền.

## 10. Rủi ro

| Rủi ro | Đối sách |
|---|---|
| PyInstaller + native ML libs (ctranslate2/onnxruntime/sherpa-onnx) khó gói | Spike đóng gói trước; `--collect-all`; test binary trên máy sạch Ubuntu |
| Tauri cần Rust + webkit2gtk trên Ubuntu | Ghi rõ prereq trong docs dev; CI cài deps |
| Handshake READY/timeout khi cold onefile extraction | Deadline 60 giây + dialog lỗi + log path |
| Đường dẫn local endpoint mở rộng attack surface | Loopback + token instance, reject traversal/link/reparse, không CORS/remote |
| Artifact chưa ký bị OS chặn | Docs vượt Gatekeeper/SmartScreen; ký số là task sau |
| Tauri file-drop khác nhau giữa OS | Verify Ubuntu; Mac/Win đánh dấu chờ verify |
