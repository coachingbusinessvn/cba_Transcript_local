# Windows Verification Checklist — ViTranscript

> Checklist verify trên **máy Windows thật** (Windows 10/11 x64), phục vụ nghiệm
> thu Task 14 (xem `docs/03-tasks.md`, tiêu chí 1 "cài trên máy sạch").
>
> **Cách đọc:** toàn bộ kết luận trong tài liệu này là **static analysis trên
> macOS x86_64 — CHƯA chạy trên Windows thật**. "Đã audit" nghĩa là đã đọc code
> và suy luận theo semantics Windows, không phải đã verify runtime. Cột "Tại
> sao" ghi lý do cần check hoặc lý do static analysis thấy an toàn.
>
> Các lỗi tìm được trong đợt audit này đã được vá + test (xem Phụ lục A cuối
> file). Checklist dưới đây chỉ còn các mục **không thể kết luận bằng static
> analysis** (môi trường thật, driver, AV, policy hệ thống…).

---

## A. Cài đặt (`install.bat`)

- [ ] **A1 — `install.bat` chạy được khi double-click từ Explorer.**
  - Verify: clone/copy repo về máy Windows (ZIP từ GitHub + `git clone`), double-click `install.bat`, cài xong không lỗi.
  - Tại sao: `install.bat`/`run.bat` trong repo đang lưu **LF-only** (verify bytewise: `0a`, không có `0d 0a`); `.gitattributes` (`*.bat text eol=crlf`) đã được thêm ở commit `06c8fae` nên **git clone/checkout trên Windows sẽ nhận CRLF**. Rủi ro còn lại: file tải qua **GitHub ZIP archive** (bỏ qua `eol` attribute) hoặc clone với `core.autocrlf=false` vẫn giữ nguyên LF. cmd.exe hiện đại thường vẫn parse được file LF cho script tuyến tính, nhưng khối `if errorlevel 1 ( ... )` nhiều dòng (`install.bat:5-8`) là pattern có rủi ro parse khác biệt. Nếu script chạy sai/không chạy → đổi file sang CRLF rồi kiểm lại.
  - Refs: `install.bat:1-14`, `run.bat:1-4`.
- [ ] **A2 — Nhánh cài `uv` qua PowerShell hoạt động.**
  - Verify: trên máy chưa có `uv`, chạy `install.bat` → `uv` tự cài → `uv --version` ra số phiên bản.
  - Tại sao: script gọi `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (`install.bat:7`). Rủi ro không kiểm chứng được bằng static analysis: (a) PowerShell 5.1 trên Windows cũ có thể thương lượng TLS cũ khiến `irm` fail; (b) policy AppLocker/Software Restriction có thể chặn PowerShell; (c) nếu cài uv thất bại, script vẫn chạy tiếp `uv python install` (`install.bat:10`) và báo `'uv' is not recognized` — lỗi có hiện nhưng flow không fail-fast.
  - Refs: `install.bat:4-10`.
- [ ] **A3 — `uv` được tìm thấy sau cài (PATH).**
  - Verify: sau khi install.bat xong, chạy `run.bat` ngay trong cùng phiên (không mở lại máy) → server lên được.
  - Tại sao: script prepend `%USERPROFILE%\.local\bin` vào PATH của phiên hiện tại (`install.bat:9`, `run.bat:3`) — đúng thư mục installer mặc định của uv. Nhưng nếu uv được cài bằng kênh khác (winget, scoop) vào nơi khác và chưa có trên PATH máy thật, `where uv` (`install.bat:4`) trượt → nhánh cài chạy dư nhưng vẫn đúng thư mục.
  - Refs: `install.bat:9`, `run.bat:3`.
- [ ] **A4 — `uv sync` kéo đủ wheel Windows x64.**
  - Verify: `uv sync` thành công; `uv run python -c "import onnxruntime, sherpa_onnx, faster_whisper, static_ffmpeg"` không lỗi.
  - Tại sao: pin `onnxruntime>=1.20,<1.24` (`pyproject.toml:22`) có wheel win_amd64 theo static analysis; nhưng sherpa-onnx/sherpa-onnx-core và static-ffmpeg trên Windows chỉ kiểm chứng được khi resolve + import thật (native DLL).
  - Refs: `pyproject.toml:7-24`, `app/media.py:11-28`.
- [ ] **A5 — SmartScreen / AV không chặn phiền toái.**
  - Verify: double-click `.bat` từ file ZIP tải về; ghi nhận SmartScreen ("More info → Run anyway") và cảnh báo antivirus nếu có; sau `uv sync`, Windows Defender không xóa/cách ly `ffmpeg.exe`/`ffprobe.exe` do static-ffmpeg tải về.
  - Tại sao: AV heuristic thường quét exe tải từ internet trong `%APPDATA%`/`~/.local` — không kiểm chứng được bằng static analysis.
  - Refs: `README.md` (mục Windows), `app/media.py:11-28`.

## B. Chạy app (`run.bat` + server)

- [ ] **B1 — `run.bat` mở được server + browser tự bật đúng trang.**
  - Verify: chạy `run.bat` → console in `ViTranscript đang chạy tại http://127.0.0.1:<port>` → browser mặc định tự mở `http://127.0.0.1:<port>` → UI tiếng Việt hiển thị (không lỗi font/mã).
  - Tại sao: `webbrowser.open` trên Windows dùng `os.startfile` — static analysis ổn, nhưng máy không có browser mặc định sẽ fail âm thầm (URL vẫn in ra console). Nếu `run.bat` nháy rồi đóng ngay (không có `pause` ở `run.bat:4`), mở `cmd.exe` chạy tay `uv run python -m app.server` để đọc lỗi.
  - Refs: `run.bat`, `app/server.py:520-548`.
- [ ] **B2 — Không bị Windows Firewall/SmartScreen chặn listen socket.**
  - Verify: lần chạy đầu không có popup firewall; nếu có, cho phép rồi kiểm chức UI vẫn vào được.
  - Tại sao: server bind `127.0.0.1` (`app/server.py:548`) — loopback thường không kích hoạt firewall prompt, nhưng một số endpoint-security chặn cả loopback listen.
  - Refs: `app/server.py:548`.
- [ ] **B3 — Truy cập bằng `localhost:<port>` cũng vào được.**
  - Verify: mở `http://localhost:<port>` trên browser → 200 (không phải 403).
  - Tại sao: Windows thường resolve `localhost` → `::1`; server chỉ bind IPv4 nên browser phải fallback IPv4 (Happy Eyeballs) — kiểm chứng trên máy thật. Guard cho phép `localhost`/`::1`/`127.0.0.1` (`app/server.py:59`), Host `localhost:port` parse đúng qua `rsplit` (`app/server.py:77`). Static analysis: Host `[::1]:port` → `::1` được chấp nhận; Host `[::1]` không port → 403 fail-closed (chấp nhận được — browser luôn gửi port cho port không mặc định).
  - Refs: `app/server.py:59,77-78`.
- [ ] **B4 — `data_dir()` tạo đúng `%APPDATA%\ViTranscript`.**
  - Verify: sau khi chạy, kiểm `C:\Users\<user>\AppData\Roaming\ViTranscript\` có `models/`, `jobs/`, `settings.json`.
  - Tại sao: `config.py:70-71` đọc env `APPDATA` với fallback `~/AppData/Roaming` — static analysis đúng. Edge chưa chắc: nếu `APPDATA` tồn tại nhưng rỗng (hiếm) → `Path("")` → thư mục tương đối theo CWD; roaming-profile/redirected-folder cũng là biến môi trường.
  - Refs: `app/config.py:66-76`.
- [ ] **B5 — GC khởi động (janitor) không crash khi gặp file bị khóa/read-only.**
  - Verify: tạo sẵn job cũ >30 ngày trong `jobs/` (sửa mtime `status.json`), đặt một file trong job ở trạng thái read-only hoặc mở file đó bằng app khác, khởi động server → server vẫn lên, log `GC jobs/: không xóa được …` cảnh báo chứ không crash.
  - Tại sao: `shutil.rmtree` trên Windows ném `PermissionError` với file đang mở/read-only — đã được catch (`app/janitor.py:107-111`) nên static analysis: skip êm, không crash. Cần verify hành vi thật vì read-only attribute là khác biệt Windows-only.
  - Refs: `app/janitor.py:103-114`, `app/server.py:535-544`.

## C. Luồng upload → transcribe → export

- [ ] **C1 — Upload file MP3 nhỏ → job chạy → transcript xong.**
  - Verify: full flow qua UI (model `phowhisper-small` — lần đầu sẽ tải ~490 MB).
  - Tại sao: verify end-to-end các tầng đã audit riêng lẻ: streaming upload ghi `input<suffix>` (`app/server.py:344-360`), ffmpeg convert (`app/media.py:55-91`), transcribe (`app/transcribe.py`), export (`app/export.py`).
- [ ] **C2 — Download model (HF) hoạt động không cần Developer Mode.**
  - Verify: xóa `models/` trong data dir → chạy job → model tải về và transcribe được.
  - Tại sao: `huggingface_hub` cache dùng symlink `blobs/` → `snapshots/`; trên Windows không có quyền symlink nó fallback sang copy (tốn gấp đôi đĩa, có warning) — static analysis: vẫn chạy, nhưng cần xác nhận không crash và chỉ báo warning.
  - Refs: `app/transcribe.py:31-36`, `app/config.py:157-164`.
- [ ] **C3 — Download model diarization hoạt động; file `.part`/`tar.bz2` sót lại không làm kẹt lần sau.**
  - Verify: chạy job bật diarization → 2 model tải về `diarization/`; (tùy chọn) giả lập crash: tạo `segmentation.tar.bz2` rỗng trong `diarization/` khi `model.onnx` chưa có → chạy lại → phải tải lại bình thường (đã vá bằng `os.replace`, `app/diarize.py:63`).
  - Tại sao: `urllib.request.urlopen` tự đọc proxy từ registry Windows — static analysis ổn; còn rủi ro proxy công ty/SSL-inspect phá TLS → verify môi trường thật. `tarfile.extractall(filter="data")` cần Python ≥3.10.12 — uv cài 3.12 nên ổn (`app/diarize.py:76`).
  - Refs: `app/diarize.py:48-80`.
- [ ] **C4 — ffmpeg chạy được: `duration_seconds` trả số, convert ra `audio16k.wav`.**
  - Verify: job video mp4 → có `audio16k.wav` + nút "Tải audio đã tách" hiện; nếu máy không có ffmpeg → static-ffmpeg tự tải exe về (check `ffmpeg.exe`/`ffprobe.exe` được tạo trong venv/static-ffmpeg dir).
  - Tại sao: `shutil.which` resolve `.exe` qua PATHEXT (static analysis: ổn); static-ffmpeg trên Windows tải zip chứa exe — SmartScreen/AV có thể chặn exe unsigned → chỉ kiểm chứng máy thật. Arg list (không `shell=True`) → không có quoting bug.
  - Refs: `app/media.py:11-28,55-91`.
- [ ] **C5 — Export 4 định dạng + đặt tên file đúng; file mở được bằng app Windows.**
  - Verify: export DOCX/XLSX/SRT/TXT → file tải về trong Downloads; mở DOCX bằng Word/WPS, XLSX bằng Excel, SRT bằng trình phát video + Notepad, TXT bằng Notepad → **dấu tiếng Việt hiển thị đúng**.
  - Tại sao: tên file đi qua `_safe_stem` (`app/server.py:457-466`) — đã lọc ký tự cấm + tên thiết bị (fix). Còn lại không chắc bằng static analysis: TXT/SRT ghi UTF-8 **không BOM** (`app/export.py:109,120`) — Notepad Win10+ đọc được nhưng một số trình phát video cũ có thể lỗi dấu → ghi nhận, nếu lỗi cân nhắc thêm BOM.
  - Refs: `app/server.py:457-466,478-492,517`, `app/export.py`.
- [ ] **C6 — Job `running` kẹt do đóng cửa sổ console giữa chừng được phục hồi.**
  - Verify: đang chạy job → đóng hẳn cửa sổ CMD (không Ctrl+C) → mở lại `run.bat` → vào job cũ → status `error` + transcript một phần (nếu có `partial.jsonl`).
  - Tại sao: đóng cửa sổ console trên Windows = kill process (không có SIGTERM) — `_get_job` đọc `status.json` + `partial.jsonl` (`app/server.py:401-449`); thread daemon không giữ process (`app/server.py:387-388`). Static analysis: đúng thiết kế, verify UX thật.
  - Refs: `app/server.py:387-388,401-449`, `app/checkpoint.py`.

## D. Edge cases

- [ ] **D1 — Tên file có dấu tiếng Việt / Unicode (`họp tháng 9.mp3`, `会议.mp4`).**
  - Verify: upload file tên có dấu → job nhận đúng tên hiển thị; export ra file có tên có dấu, tải về mở được; transcript không lỗi.
  - Tại sao: filename chỉ đi vào `job["filename"]` + `_safe_stem` — filesystem chỉ thấy `input<suffix>` (`app/server.py:307,349`) nên static analysis: an toàn. ffmpeg trên Windows nhận argv Unicode (wmain→UTF-8) — thường ổn, nhưng chỉ kiểm chứng máy thật; browser gửi basename không gửi full path.
  - Refs: `app/server.py:307,327,349,457-466`.
- [ ] **D2 — Tên file trùng tên thiết bị Windows (`CON.mp3`, `NUL.wav`, `com1.m4a`, `con.heo.mp3`).**
  - Verify: upload `CON.mp3` → export → file tải về tên `_CON.docx` (không phải `CON.docx`), không lỗi 500; upload `con.heo.mp3` → `_con.heo.docx` (Windows match tên thiết bị trên component trước dấu chấm đầu tiên của tên file).
  - Tại sao: đã vá `_safe_stem` + test (`_WIN_DEVICE_STEMS`, `app/server.py:65-69,464-465`; test `tests/test_core.py::test_safe_stem_avoids_windows_device_names`). Trên POSIX test pass được vì chỉ kiểm stem trả về; **verify thật trên Windows** rằng không còn lỗi ghi file.
  - Không cover (exotic — chỉ ghi nhận, verify-only): `CONIN$`/`CONOUT$`/`CLOCK$` và dạng superscript `COM¹`/`COM²`/`COM³` (Windows map về COM1/2/3) KHÔNG nằm trong `_WIN_DEVICE_STEMS`; cũng không xử lý component đầu có trailing space (`con .heo.docx`).
  - Refs: `app/server.py:65-69,457-466`.
- [ ] **D3 — File input đang mở bởi app khác / file trong thư mục OneDrive.**
  - Verify: upload file đang mở (vd video đang phát trong player); file nằm trong OneDrive "Files On-Demand" (placeholder) → upload + chạy bình thường.
  - Tại sao: upload đọc stream HTTP (không đọc file gốc trực tiếp) nên khóa file không ảnh hưởng; OneDrive placeholder được tải về trong lúc đọc — hành vi OS, không kiểm chứng bằng static analysis.
  - Refs: `app/server.py:344-353`.
- [ ] **D4 — Antivirus/Defender quét file `.onnx`/`model.bin` tải về.**
  - Verify: sau tải model, AV không cách ly file model; job không lỗi "model hỏng" sau quét.
  - Tại sao: AV có thể khóa file trong lúc ghi → `_download`/`snapshot_download` fail giữa chừng; sha256 check (`app/diarize.py:53-59`, `app/punctuate.py:38-46`) sẽ bắt file hỏng và báo lỗi rõ — nhưng chỉ kiểm chứng máy thật.
  - Refs: `app/diarize.py:48-80`, `app/punctuate.py:32-76`, `app/config.py:57-63`.
- [ ] **D5 — Chạy từ thư mục có dấu/khoảng trắng/UNC trong đường dẫn.**
  - Verify: đặt repo vào `D:\thư mục có dấu\` → `install.bat` + `run.bat` hoạt động; (tùy chọn) chạy từ `\\server\share` → xác nhận `cd /d "%~dp0"` fail đúng cách với thông báo hiểu được.
  - Tại sao: `%~dp0` quote đúng (`install.bat:2`, `run.bat:2`) — static analysis: an toàn cho khoảng trắng/dấu. UNC path là hạn chế cmd.exe (`CMD does not support UNC paths as current directories`) — hành vi mong đợi, chỉ cần ghi nhận.
  - Refs: `install.bat:2`, `run.bat:2`.
- [ ] **D6 — Export khi file đích đang mở (job cũ export 2 lần).**
  - Verify: export docx → mở file docx trong Word (không đóng) → export lại cùng định dạng → kiểm chức app báo lỗi rõ hoặc ghi đè được, không 500 mù mờ.
  - Tại sao: export ghi `job_dir/{stem}.{fmt}` (`app/server.py:489`) — nếu file đang mở trong Word, ghi đè trên Windows ném `PermissionError` → route trả 500 (traceback log). Static analysis: lỗi hiện rõ, không mất dữ liệu — mức chấp nhận được; verify UX thật.
  - Refs: `app/server.py:478-492`, `app/export.py:58,96,109,120`.
- [ ] **D7 — `os.replace` ghi `status.json` khi file đang được đọc đồng thời.**
  - Verify: khó kiểm chứng trực tiếp (race window nhỏ) — dùng đợt chạy job dài quan sát log có `Không ghi được status job` không.
  - Tại sao: trên Windows, `os.replace` lên file đang mở (không share-delete) có thể ném `PermissionError` — đã catch và degrade êm (giữ job trong RAM, `app/server.py:160-179,259-261`). Static analysis: an toàn, chỉ cần ghi nhận log.
  - Refs: `app/server.py:160-179`.

## E. Unit tests trên Windows (dev)

- [ ] **E1 — `uv run pytest tests/ -x -q` xanh trên Windows.**
  - Verify: chạy suite; test symlink đã `skipif(os.name=="nt")` (`tests/test_janitor.py:243`) nên không cần admin; test live-server bind loopback không bị firewall chặn (`tests/test_server_live.py:28`).
  - Tại sao: sau fix, không còn assertion phụ thuộc parse path POSIX: test `_safe_stem` chỉ assert bất biến đúng trên cả hai OS (stem không rỗng, không chứa `\ / :`) vì `Path().stem` parse `\` khác nhau giữa POSIX (không phải separator) và Windows (là separator). `tempfile.TemporaryDirectory` đều đóng file đúng. Mọi test của audit này (device-name, clobber-rename, reparse-tag) mô phỏng semantics Windows bằng monkeypatch nên chạy được trên cả hai OS. Phụ thuộc platform còn lại (đã ghi trong code): `test_reparse_point_job_dir_skipped` chỉ meaningful trên Python ≥3.11 — trên 3.10 `Path.lstat` bind `os.lstat` qua `_accessor` nên monkeypatch `os.stat` không chặn được và test sẽ fail (uv pin 3.12); `test_symlinked_job_dir_not_removed` skip trên `nt`; live-server bind `127.0.0.1` thật.
  - Refs: `tests/test_janitor.py:243`, `tests/test_server_live.py:18-53`, `tests/test_core.py`.
- [ ] **E2 — KHÔNG chạy `scripts/smoke_e2e.py` trên Windows.**
  - Verify: bỏ qua script này (dùng `say` của macOS); thay bằng C1–C5 ở trên.
  - Refs: `scripts/smoke_e2e.py`.

---

## Phụ lục A — Các fix đã vá trong đợt audit này (có test)

| # | Lỗi | Fix | Test |
|---|-----|-----|------|
| 1 | `_safe_stem` không lọc tên thiết bị Windows (`CON.mp3` → `CON.docx`; `con.heo.mp3` → `con.heo.docx` — Windows match component trước dấu chấm đầu tiên — mở device thay vì tạo file) | Thêm `_WIN_DEVICE_STEMS`, prefix `_` khi component đầu của stem trùng — `app/server.py:65-69,464-465` | `test_safe_stem_avoids_windows_device_names` |
| 2 | `diarize._download` dùng `tmp.rename(dest)` — Windows ném `FileExistsError` khi dest còn sót từ lần tải bị kill → mọi lần chạy sau lỗi | `tmp.replace(dest)` — `app/diarize.py:60-63` | `test_download_clobbers_leftover_dest` (mô phỏng rename-no-clobber bằng monkeypatch `os.rename`) |
| 3 | janitor chỉ check `is_symlink()` — junction/reparse point (Windows) trượt; `rmtree` trên Python <3.12 đi theo junction xóa target ngoài `jobs/` | Bỏ qua entry có `st_reparse_tag` ≠ 0 — `app/janitor.py:68-73` | `test_reparse_point_job_dir_skipped` (mô phỏng reparse tag qua `os.stat`) |
| 4 | UI báo "mở lại app (run.command)" — người dùng Windows không có file đó | Sửa text "run.command trên macOS / run.bat trên Windows" — `app/static/index.html:668-669` | — (text tĩnh) |

## Phụ lục B — Vùng đã audit, KHÔNG thấy lỗi (static analysis)

| Vùng | Kết luận static analysis |
|------|--------------------------|
| Host parsing `_security_guard` (`app/server.py:77`) | `[::1]:port` → `::1` đúng; bare `[::1]`/`::1` không bracket → 403 fail-closed (chấp nhận được); `localhost:port`, `127.0.0.1:port`, FQDN trailing dot → đúng. `::1` có trong `_ALLOWED_HOSTS` (`:59`). |
| `_JOB_ID_RE` hex-12 (`app/server.py:57,151`) | Chỉ `[0-9a-f]` — không chứa `\`, `/`, `.` → không thể traversal trên Windows. |
| Upload byte-cap streaming (`app/server.py:344-360`) | File `input<suffix>` đóng trong `with` trước `unlink` (`:396`) → unlink trên Windows ổn; cap 8 GB đếm byte không phụ thuộc Content-Length. |
| `os.replace` status write (`app/server.py:172-175`) | tmp đóng trước replace; race đọc-đồng-thời trên Windows → `PermissionError` → catch → degrade êm (giữ RAM). |
| `extracted_audio` containment (`app/server.py:509-517`) | `resolve()` + `is_relative_to()` — pathlib Windows casefold xử lý case drive letter; `\\?\` verbatim trong status.json → fail-closed 404. |
| `_free_port`/`main()` (`app/server.py:520-548`) | `connect_ex` loopback semantics giống POSIX; `webbrowser.open` dùng URL literal `127.0.0.1` — không phụ thuộc resolve `localhost`. |
| `janitor` rmtree (`app/janitor.py:103-114`) | `PermissionError`/read-only → catch → skip êm, không crash server. |
| subprocess (`app/media.py`) | Toàn bộ arg list, không `shell=True`; `shutil.which` resolve `.exe` qua PATHEXT. |
| `tarfile.extractall(filter="data")` (`app/diarize.py:76`) | `filter` có từ Python 3.10.12/3.11.4/3.12 — uv pin 3.12. |
| `pipeline` filename (`app/pipeline.py:35-36`) | Input luôn là `input<suffix>` do server đặt → stem an toàn, không mang filename người dùng. |
| `.bat` encoding | Bytewise: ASCII, không dấu tiếng Việt (`file`: "ASCII text") — đúng constraint. |
| `tests/` | Không hardcoded `/` trong path assertion; symlink test đã skip trên `nt`. |
| `index.html` fetch paths | Toàn bộ relative (`/api/...`) — không phụ thuộc host/OS. |
