# Plan: ViTranscript Desktop (Tauri + Python sidecar)

> Spec: [../specs/2026-08-10-desktop-tauri-design.md](../specs/2026-08-10-desktop-tauri-design.md)
> Supersedes: `docs/09-spec-desktop-shell.md` (browser + pystray, chưa triển khai).
> Ngày finalize: 2026-08-10. Phạm vi verify vòng này: **Ubuntu x86_64**.
> Trạng thái: **đã review, không còn điểm mở về kiến trúc/triển khai**.

## Quyết định đã chốt

### 1. PyInstaller và native libraries

- Dùng **PyInstaller onefile cho sidecar release** vì Tauri `externalBin` đóng gói một
  executable theo target triple; PyInstaller onedir cần cả thư mục `_internal` nằm cạnh
  executable và không khớp ổn định với layout bundle của Tauri trên ba OS.
- Vẫn build **onedir chẩn đoán** trong Task 1 để nhìn rõ file `.so`/`.dll`/`.dylib`, sửa
  hook nhanh và chạy import probe. Chỉ khi onedir pass mới build onefile từ cùng một
  `Analysis`; artifact Tauri luôn dùng onefile.
- PyInstaller `EXE` giữ `console=True`, `upx=False`. Trên Windows, Tauri spawn với
  `CREATE_NO_WINDOW` và redirect stdout/stderr; như vậy không flash console nhưng READY
  vẫn đọc được. Không dùng PyInstaller `windowed/noconsole` vì sẽ làm hỏng handshake.
- Pin build tool trong group `desktop`: `pyinstaller==6.21.0` và
  `pyinstaller-hooks-contrib==2026.6`; commit `uv.lock`. Build bằng Python 3.12 từ
  `.python-version`, trong môi trường chỉ có dependency của project + group `desktop`.
- File spec dùng `collect_all()` cho các import package:
  `ctranslate2`, `onnxruntime`, `sherpa_onnx`, `tokenizers`, `faster_whisper`, `av`,
  `static_ffmpeg`. Hợp nhất/deduplicate cả ba danh sách `datas`, `binaries`,
  `hiddenimports` do `collect_all()` trả về.
- Thêm hidden import tường minh cho các import động quan trọng:
  `ctranslate2`, `onnxruntime`, `onnxruntime.capi._pybind_state`, `sherpa_onnx`,
  `tokenizers`, `faster_whisper`, `faster_whisper.transcribe`, `av`,
  `static_ffmpeg.run`. Không collect `transformers`, `torch`, `tensorflow`.
- `sherpa-onnx-core` không được giả định có import package riêng. Spec phải đọc file từ
  distribution metadata `sherpa-onnx-core`, đưa mọi `.so`, `.dylib`, `.dll`, `.pyd`
  vào `binaries` và giữ nguyên relative parent; copy metadata của cả `sherpa-onnx` và
  `sherpa-onnx-core`.
- `datas` bắt buộc có `app/static/**` tại đích `app/static`, metadata cần cho các package
  native, và asset runtime của `faster_whisper` (bao gồm VAD ONNX) do `collect_all()`
  phát hiện.
- Không trông chờ `static-ffmpeg` tải binary lúc chạy. Build script gọi API của package
  để resolve/download đúng `ffmpeg` + `ffprobe` cho build host, ghi version + SHA-256,
  rồi add hai executable vào `binaries` dưới `ffmpeg/`. Khi `sys.frozen` tồn tại,
  `app.media` ưu tiên cặp đã bundle; fallback system/package chỉ áp dụng dev legacy.
- Sidecar có `--self-test-native`: import đủ bảy package trên, in version/provider,
  chạy `ffmpeg -version` và `ffprobe -version`, rồi thoát 0. Đây là gate trước `/healthz`
  và E2E model.
- Test môi trường sạch là container/VM Ubuntu 22.04 thứ hai **không mount source, không
  venv, không cài Python**; chỉ copy onefile và cài runtime OS tối thiểu đã ghi trong
  docs. Gate gồm self-test, `/healthz`, một job `tiny-test`, export non-empty, rồi chạy
  lại cùng cache với `--network none`.

### 2. Chọn port và readiness

- Tauri luôn spawn sidecar với `--port 0 --no-browser`; sidecar tự chọn port trong
  `8756..8805`; Tauri lấy port **chỉ từ dòng READY**, không áp port cố định và không tự
  đoán port.
- Sidecar không dùng mô hình “check port rồi bind”. Nó thử `bind()` trực tiếp từng port,
  giữ socket đã bind và truyền socket đó cho Uvicorn; như vậy không có race TOCTOU giữa
  dò port và Uvicorn bind.
- READY chỉ in sau `uvicorn.Server.started == True`, đúng một lần, có `flush=True`:
  `VITRANSCRIPT_READY http://127.0.0.1:<port>`.
- Tauri chỉ nhận regex chính xác `^VITRANSCRIPT_READY http://127\.0\.0\.1:(\d+)$`,
  deadline tổng 60 giây từ lúc spawn. Sau READY, poll `/healthz` mỗi 100 ms, timeout mỗi
  request 500 ms, và yêu cầu JSON trả đúng port trước khi tạo/hiện window.
- Sidecar exit trước READY, READY sai/duplicate, health sai port, hoặc hết 60 giây đều là
  lỗi startup: ghi log, shutdown process tree, hiện dialog tiếng Việt có path log.

### 3. Shutdown sidecar

- Tauri sinh token ngẫu nhiên 256 bit bằng OS RNG cho mỗi instance, truyền qua env
  `VITRANSCRIPT_INSTANCE_TOKEN` (không truyền CLI để tránh lộ trong process list).
- `POST /api/shutdown` chỉ nhận loopback và header `X-ViTranscript-Token`; so sánh token
  constant-time. Token thiếu/sai trả 403; token env chưa cấu hình trả 404; hợp lệ trả
  202 rồi đặt `uvicorn.Server.should_exit = True` sau khi response được gửi.
- Khi đóng window hoặc chọn menu `Thoát`, Tauri prevent close lặp, gọi shutdown, chờ tối
  đa 5 giây và kiểm tra child exit/health không còn trả lời.
- Fallback là terminate **đúng process tree do Tauri spawn**: Unix tạo process group mới
  và signal group (TERM, chờ 2 giây, rồi KILL); Windows gán child vào Job Object có
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Không `pkill`, không `taskkill /IM`, không kill
  theo tên và không dò process toàn hệ thống.
- Token endpoint là đường graceful chính; process group/Job Object cũng bảo đảm sidecar
  chết nếu Tauri crash. Job Python đang chạy là daemon và checkpoint hiện có giữ hành vi
  phục hồi file dài.

### 4. Bảo mật `POST /api/jobs/local`

- Endpoint bắt buộc đồng thời: peer socket là loopback **và** instance token đúng như
  shutdown. Không tin `Host`, `Origin`, `X-Forwarded-For`; chạy Uvicorn với
  `proxy_headers=False`; không thêm CORS.
- JSON body chứa `path` cùng đầy đủ option của upload:
  `model`, `language`, `diarize`, `punctuate`, `num_speakers`, `glossary`. Hai endpoint
  dùng chung helper reserve/start job để 409, long-audio policy, settings và cleanup có
  cùng semantics.
- Validate theo đúng thứ tự, trước khi reserve job:
  1. path là string không rỗng, không NUL, là absolute path;
  2. reject mọi component `..` trước `resolve()`;
  3. `lstat()` từng component từ anchor tới file, reject symlink; trên Windows reject
     thêm component có `FILE_ATTRIBUTE_REPARSE_POINT` (junction/reparse point);
  4. `resolve(strict=True)`; require regular file bằng `stat` (không directory, FIFO,
     socket, device);
  5. suffix lowercase thuộc `media.AUDIO_EXTS | media.VIDEO_EXTS`.
- Không giới hạn file vào home/data dir vì dialog hợp lệ phải mở được file ở volume bất
  kỳ. Backend đọc trực tiếp source đã canonicalize, nhưng mọi output/checkpoint vẫn ghi
  vào `jobs/<job_id>/`; không ghi cạnh file nguồn và không xóa/đổi tên file nguồn.
- Path từ UI không được gửi bằng fetch trực tiếp. JS gọi Tauri command hẹp; Rust giữ token
  trong memory và POST sang backend. Token không được đưa vào DOM/localStorage/log.
- Rust giữ một grant-set in-memory chỉ gồm path do native picker/drop tạo trong instance
  hiện tại; `start_local_job` reject path không có trong grant-set. Vì vậy script trong
  webview không thể tự đặt path tùy ý dù gọi được custom command.
- Residual TOCTOU nếu một local process có quyền thay file sau validation được ghi rõ là
  rủi ro chấp nhận của v1; token per-instance + reject link/reparse giảm attack surface
  thực tế, không mở rộng thành sandbox/copy file trong vòng này.

### 5. System tray

- **Bỏ tray khỏi vòng này.** Window native + menu `File > Thoát` đã đủ; close window có
  semantics thoát app nên tray `Mở cửa sổ` không có vòng đời hữu ích.
- Bỏ tray tránh thêm AppIndicator behavior khác nhau giữa Linux/macOS/Windows và giảm
  một hạng mục không thể verify đáng tin cậy trong headless Ubuntu. Không bật Tauri
  `tray-icon` feature, không có logic “close để hide”. Tray có thể là task độc lập sau
  nếu người dùng yêu cầu app chạy nền.

## Nguyên tắc thực thi

- TDD cho backend: viết test, chạy thấy fail đúng lý do, mới sửa implementation; không
  commit trạng thái red.
- Mỗi task: code → verify hẹp → `uv run ruff check .` → test liên quan → cập nhật context
  nếu thuộc mandatory rule → commit.
- Commit trailer bắt buộc:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Giữ core: chỉ `127.0.0.1`, một job (409), không PyTorch/TensorFlow, `names` key string,
  typo upstream không đổi, script Windows ASCII-only.
- Không ký số/notarize, auto-update, bundle model, multi-job, multi-instance hoặc thêm
  framework frontend.
- Không đánh dấu PASS macOS/Windows từ compile tĩnh hoặc kết quả Ubuntu.

## Hợp đồng public cần giữ ổn định

| Thành phần | Hợp đồng |
|---|---|
| Sidecar CLI | `--port 0..65535`, `--no-browser`, `--self-test-native` |
| Readiness | một dòng `VITRANSCRIPT_READY http://127.0.0.1:<port>` sau server started |
| Health | `GET /healthz` → 200 `{"status":"ok","port":<actual>}` |
| Local job | `POST /api/jobs/local`, loopback + token, body path + option, 200 job id |
| Shutdown | `POST /api/shutdown`, loopback + token, 202 rồi graceful exit |
| Upload cũ | `POST /api/jobs` multipart giữ nguyên và vẫn chạy trong browser |
| Sidecar env | `VITRANSCRIPT_INSTANCE_TOKEN`, `VITRANSCRIPT_DESKTOP=1`; test-only `VITRANSCRIPT_ENABLE_TEST_MODEL=1` |

`VITRANSCRIPT_ENABLE_TEST_MODEL=1` đăng ký key `tiny-test` → source `tiny` chỉ trong
process test. Tauri production không set env này; `tiny-test` không xuất hiện cho user.

## Task 0 — Backend desktop contract theo TDD

**Files:** `app/server.py`, `app/server_runtime.py`, `app/media.py`, `app/config.py`,
`tests/test_server_desktop.py`.

### 0.1 Viết test trước

1. CLI parser: absent/`0` chọn dynamic; fixed port hợp lệ được giữ; `<0`, `>65535`, text
   trả lỗi argparse.
2. Socket bind: port đầu bị chiếm thì chọn port sau; fixed port bị chiếm fail rõ; socket
   được giữ tới khi Uvicorn nhận nên không có khoảng trống race.
3. Subprocess contract: chạy `python -m app.server --port 0 --no-browser`, đọc READY
   trong deadline, khẳng định đúng một dòng, `/healthz` trả actual port, browser không mở.
4. Shutdown: non-loopback 403; token thiếu/sai 403; không cấu hình token 404; token đúng
   202 và callback shutdown được gọi đúng một lần.
5. Local endpoint happy path: IPv4 `127.0.0.1` và IPv6 `::1`, token đúng, option đầy đủ,
   trả job id; pipeline nhận source canonical và output dir là `jobs/<id>`.
6. Local endpoint reject: non-loopback; token thiếu/sai; relative; NUL; `..`; missing;
   directory; unsupported suffix; FIFO (POSIX); symlink file; symlink parent; Windows
   reparse helper bằng mock.
7. Parity với upload: model sai 400; active job 409; thread start/preparation fail phải
   nhả reservation; long-audio policy và settings/glossary dùng chung.
8. OPTIONS/cross-origin không nhận header CORS; forged `X-Forwarded-For` không thay đổi
   peer được auth helper nhìn thấy.
9. `--self-test-native` có unit test bằng monkeypatch imports/ffmpeg, không tải model.

### 0.2 Implement tối thiểu để test xanh

1. Tách runtime CLI/socket/Uvicorn readiness sang `app/server_runtime.py`; `app.server`
   tiếp tục export FastAPI `app` và `main()` để giữ command cũ.
2. Dùng bound socket + subclass/hook Uvicorn startup để print READY sau `started`; set
   actual port vào `app.state` cho `/healthz`.
3. Uvicorn khóa `host=127.0.0.1`, `workers=1`, `reload=False`, `proxy_headers=False`.
   Browser legacy chỉ mở khi không có `--no-browser`; desktop không dùng Timer/browser.
4. Thêm auth helper dùng `ipaddress.ip_address(peer).is_loopback` và
   `hmac.compare_digest`; không log token/path đầy đủ ở error không cần thiết.
5. Tạo Pydantic request model cho local job với constraint type/range. Refactor helper
   `_reserve_job`, `_prepare_and_start_job`; upload và local gọi chung helper.
6. Refactor `_run_job` nhận riêng `input_path` và `output_dir`; upload vẫn lưu input vào
   job dir, local đọc source tại chỗ, mọi generated file vào job dir.
7. Thêm frozen ffmpeg resolver và self-test CLI; behavior dev hiện tại không đổi.
8. Thêm test-only model env gate trong config/server startup, không sửa production
   `MODEL_REGISTRY` mặc định.

**Verify:**

```bash
uv run pytest tests/test_server_desktop.py -v
uv run pytest tests/ -v
uv run ruff check .
```

Manual subprocess verify phải ghi lại READY, JSON health, exit code sau shutdown; không
chấp nhận chỉ test helper format string.

## Task 1 — Spike PyInstaller native libs (BLOCKER)

**Files:** `desktop/pyinstaller/sidecar_entry.py`,
`desktop/pyinstaller/vitranscript-sidecar.spec`,
`desktop/scripts/build-sidecar.sh`, `desktop/scripts/build-sidecar.ps1`,
`pyproject.toml`, `uv.lock`, `THIRD_PARTY_NOTICES.md`.

1. Thêm group `desktop` với đúng hai build tool đã pin, chạy lock/sync và assert dependency
   tree không có torch/tensorflow trước khi viết spec.
2. `sidecar_entry.py` chỉ import/call `app.server.main`; không duplicate CLI logic.
3. Spec tạo một `Analysis` dùng các collect/hidden import/binary đã chốt. Có argument
   sau `--` là `--mode onedir|onefile`; hai mode dùng cùng Analysis để không drift.
   Cả hai giữ `console=True`, `upx=False`; onefile là output release duy nhất.
4. Build luôn `--clean --noconfirm`; build script fail nếu environment có distribution
   `torch` hoặc `tensorflow`, hoặc nếu warn file có missing module thuộc danh sách native.
5. Resolve và bundle `ffmpeg`/`ffprobe`; ghi manifest JSON cạnh dist gồm OS, arch, Python,
   package versions, ffmpeg hashes và sidecar hash. Không chứa secret/path cá nhân.
6. Chạy onedir `--self-test-native`, server readiness/shutdown; sau đó onefile chạy lại
   cùng gate. So sánh provider/import output, không chỉ kiểm file tồn tại.
7. Build Linux release trong Ubuntu 22.04 container để giữ baseline glibc; host hiện tại
   Ubuntu 26.04 chỉ dùng để chạy compatibility smoke, không phát hành artifact build trực
   tiếp từ host.
8. Sinh WAV speech trước bằng `espeak-ng -v vi` + ffmpeg rồi chỉ copy WAV và onefile vào
   fresh Ubuntu 22.04 runtime container không Python/venv/source. Container chỉ cài
   runtime OS tối thiểu đã document; sine/silence không đủ vì export cần câu transcript.
9. Với env test model + token đã biết, POST `/api/jobs/local`, poll done, export TXT và
   require file non-empty. Chạy lần đầu có network để cache model; container thứ hai dùng
   cùng `XDG_DATA_HOME`, `--network none`, chạy lại job và export.
10. Audit license/provenance của binary ffmpeg thực tế; cập nhật third-party notice trước
   khi artifact được coi là distributable.

**Gate:** dừng trước Tauri nếu bất kỳ import native, ffmpeg, health, tiny job hoặc offline
rerun fail. Báo rõ package/file thiếu; không chữa bằng cài library Python trên runtime
container.

**Bằng chứng lưu trong log CI/PR:** sidecar SHA-256, kích thước onefile/onedir, self-test
JSON, READY/health, job id, export size, danh sách package không có torch/tensorflow.

## Task 2 — Tauri shell và lifecycle

**Files:**

- `desktop/frontend/index.html` (placeholder duy nhất; không phải UI sản phẩm);
- `desktop/src-tauri/Cargo.toml`, `Cargo.lock`, `build.rs`, `tauri.conf.json`;
- `desktop/src-tauri/src/{main.rs,sidecar.rs}`;
- `desktop/src-tauri/capabilities/desktop-remote.json`.

1. Dùng Tauri v2, Rust edition 2021, version constraint major 2 và commit `Cargo.lock`;
   pin Tauri CLI `2.11.4` trong script/CI. Không thêm Node/package manager.
2. `tauri.conf.json`: identifier `vn.coachingbusiness.vitranscript`, product
   `ViTranscript`, `frontendDist: ../frontend`, không khai báo main window tĩnh. Window
   chỉ được tạo programmatically sau health pass, URL là exact READY origin.
3. `bundle.externalBin: ["binaries/vitranscript-sidecar"]`. Build script phải stage:

   | Build host | File bắt buộc |
   |---|---|
   | Ubuntu x64 | `binaries/vitranscript-sidecar-x86_64-unknown-linux-gnu` |
   | macOS arm64 | `binaries/vitranscript-sidecar-aarch64-apple-darwin` |
   | macOS Intel | `binaries/vitranscript-sidecar-x86_64-apple-darwin` |
   | Windows x64 | `binaries/vitranscript-sidecar-x86_64-pc-windows-msvc.exe` |

   Triple lấy bằng `rustc --print host-tuple`; build script fail nếu output PyInstaller
   arch khác triple, không cross-copy binary.
4. Rust resolve external binary đã bundle cạnh `current_exe`, không dựng path từ triple ở
   runtime. Unix spawn bằng `std::process::Command` + `CommandExt::process_group(0)`;
   Windows dùng helper `CreateProcessW` với redirected stdout/stderr và flags
   `CREATE_SUSPENDED | CREATE_NO_WINDOW` để giữ process/thread handle.
5. Trước khi sidecar được chạy: Unix đã có process group từ pre-exec; Windows tạo Job
   Object `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign suspended process rồi mới
   `ResumeThread`. Sau đó set env token, desktop/unbuffered flags và args
   `--port 0 --no-browser`; lưu lifecycle state gồm child/process handle, group/job,
   token, READY URL, port, log path, `shutting_down`.
6. Reader task ghi nguyên stdout/stderr vào app log dir và gửi line stdout vào readiness
   parser. Mirror READY line sang stdout Tauri để headless smoke khám phá port; tuyệt đối
   không mirror token.
7. Áp deadline/poll contract đã chốt; chỉ sau health pass mới tạo main webview
   `1100x760`, min `900x650`, title `ViTranscript`, URL loopback exact, rồi show/focus.
8. Chặn navigation top-level ra ngoài exact loopback origin. Link tài liệu mở bằng OS
   browser qua URL allowlist cụ thể, không cho webview navigate sang remote site.
9. Close event và menu exit đi qua một hàm shutdown idempotent; dialog startup error ghi
   lý do ngắn + log path; app exit luôn reap child/process tree.

### Rust tests không cần display

- READY parser: chunk split giữa nhiều event, CRLF/LF, malformed URL, non-loopback,
  duplicate READY.
- Deadline: child exit trước READY và timeout tạo đúng startup error.
- Health validator reject status/port sai.
- Shutdown state idempotent: hai close event chỉ gửi một request/kill sequence.
- Sidecar path mapping đúng bốn target triple và `.exe` chỉ trên Windows.
- OS integration helper: fallback kill process group/Job Object làm chết cả child forked,
  không chạm process không thuộc group/job.

**Verify:** `cargo test --manifest-path desktop/src-tauri/Cargo.toml` và
`cargo check --manifest-path desktop/src-tauri/Cargo.toml` xanh trước khi cần display.

## Task 3 — Native file bridge, menu và queue UI

**Files:** `desktop/src-tauri/src/{main.rs,native.rs}`, `app/static/index.html`, capability
file của Task 2.

1. Remote capability chỉ match window `main` + URL `http://127.0.0.1:*`; expose đúng các
   custom command/event cần thiết. JS không được quyền shell, filesystem tổng quát hoặc
   đọc token. Bật global Tauri API vì frontend là HTML tĩnh, nhưng Rust chỉ register:
   `pick_local_files` và `start_local_job`.
2. `pick_local_files`: Rust mở dialog native, filter đúng ext từ media contract, cho chọn
   nhiều file, require absolute path, thêm path gốc vào grant-set in-memory rồi trả
   ordered list. Không `canonicalize()` ở Rust vì backend cần thấy path gốc để reject
   symlink/reparse. Menu `File > Mở…` gọi cùng helper và emit list cho main window.
3. Native drag-drop chỉ nhận file paths; bỏ directory/URL; emit ordered list. Rust không
   đọc nội dung file và không tự start job; path hợp lệ được thêm grant-set trước khi emit.
4. `start_local_job(path, options)`: Rust POST JSON tới exact READY origin, thêm token
   header, nhưng reject trước nếu path không nằm trong grant-set. Dùng timeout connect
   ngắn nhưng không timeout toàn pipeline (request chỉ enqueue), trả nguyên status/body
   cần thiết cho JS. Không accept arbitrary URL/path chưa grant từ frontend.
5. UI có hai mode rõ ràng:
   - trong Tauri: click vùng chọn gọi native command, drag-drop dùng native event, submit
     local path qua Rust command, không tạo multipart upload;
   - browser legacy: giữ nguyên `<input type=file>` + multipart `/api/jobs`.
6. Queue native: picker/drop nhiều file append theo thứ tự, deduplicate theo platform path
   string mà Rust đã grant, hiển thị `chờ/chạy/xong/lỗi`; snapshot option khi bấm Start;
   chỉ submit item kế tiếp sau item hiện tại terminal để không tạo 409. Lỗi một item được
   ghi nhận rồi tiếp tục.
7. Click item đã xong tải status và hiển thị transcript/export hiện có; queue không cần
   persist qua restart trong v1. Mọi filename/path render bằng `textContent`, không
   `innerHTML`/eval.
8. Menu native:
   - `File > Mở…` — enqueue;
   - `File > Thoát` — lifecycle shutdown;
   - `Trợ giúp > Giới thiệu` — dialog version/app name;
   - `Trợ giúp > Tài liệu` — URL cố định tới README repository bằng opener allowlist.
9. Không tạo tray, không intercept close để hide, không có trạng thái background.

**Verify Ubuntu interactive (bắt buộc, không giả lập bằng unit):** mở picker, chọn file
ngoài home nếu có volume test, drop 2 file, thấy queue chạy tuần tự không 409, menu About,
Docs, close window và xác nhận không còn sidecar. Ghi checklist + screenshot/log vào PR.

## Task 4 — Icon, build scripts, bundler và CI đa nền tảng

**Files:**

- `desktop/icons/vitranscript-1024.png`;
- `desktop/src-tauri/icons/*`;
- `desktop/src-tauri/tauri.{linux,macos,windows}.conf.json`;
- `desktop/scripts/build-linux.sh`, `build-macos.sh`, `build-windows.ps1`;
- `.github/workflows/desktop-build.yml`, `.gitignore`.

1. Tạo source icon vuông 1024x1024, không transparent toàn phần; chạy
   `cargo tauri icon` để sinh PNG sizes, `.ico`, `.icns`; config tham chiếu đúng file.
2. Config common không chứa target bundle chéo OS. Script truyền config platform:
   Linux `appimage,deb`; macOS `app,dmg`; Windows `nsis` (main `.exe` nằm ở release output
   và NSIS installer nằm trong bundle).
3. Mỗi script theo một pipeline cố định:
   `uv sync --frozen --group desktop` → test/self-test cần thiết → PyInstaller onefile →
   tính triple + stage externalBin → verify SHA/execute bit →
   `cargo tauri build --no-sign --config <platform-config>` → liệt kê artifact + SHA-256.
4. Script xóa đúng stale staged sidecar/target copy trước build, không `cargo clean` toàn
   repo mặc định. Fail nếu staged checksum khác output PyInstaller.
5. Ubuntu dev/build dependencies ghi đúng và CI cài: `libwebkit2gtk-4.1-dev`,
   `build-essential`, `curl`, `wget`, `file`, `libxdo-dev`, `libssl-dev`,
   `libayatana-appindicator3-dev`, `librsvg2-dev`; thêm `xvfb`, `xdotool`, `espeak-ng`
   cho test. App không dùng tray dù package prereq chính thức có appindicator.
6. Linux release build chạy `ubuntu-22.04`, không `ubuntu-latest`, để giữ glibc baseline.
   Test artifact thêm trên host Ubuntu 26.04 hiện tại để chứng minh forward compatibility.
7. CI matrix wire đúng bốn target, native build từng host (PyInstaller không cross-build):
   - `ubuntu-22.04` → `x86_64-unknown-linux-gnu`;
   - `macos-15` → `aarch64-apple-darwin`;
   - `macos-15-intel` → `x86_64-apple-darwin`;
   - `windows-2022` → `x86_64-pc-windows-msvc`.
8. CI Ubuntu chạy tests + package + headless smoke; Mac/Windows vòng này chỉ build/self-test
   sidecar nếu runner thực sự chạy. Dù CI xanh, DT native Mac/Win vẫn ghi “chờ máy thật”.
9. Upload artifact theo OS/arch, kèm sidecar manifest/checksums; không upload PyInstaller
   work dir, Cargo target hoặc model cache. Cache dependency được phép, cache model không.
10. PowerShell và mọi `.bat`/Windows-visible script chỉ ASCII. `Cargo.lock`, icon source,
    generated icons và config được commit; `target/`, PyInstaller `build/`/`dist/`, staged
    target-triple binaries bị ignore.

**Static verify:** parse JSON configs, `cargo metadata`, `actionlint` workflow, và assert
mọi externalBin path expected có mapping trong build scripts. Không gọi đây là PASS bundle
Mac/Win nếu workflow chưa chạy trên runner tương ứng.

## Task 5 — E2E Ubuntu và nghiệm thu headless/interactive

**Files:** `scripts/gen_test_audio_linux.sh`, `scripts/e2e_sidecar_linux.py`,
`scripts/smoke_desktop_linux.sh`.

### 5.1 Sidecar E2E headless, tự động

1. `gen_test_audio_linux.sh` dùng `espeak-ng -v vi` tạo câu 8–15 giây, dùng bundled
   ffmpeg normalize WAV 16 kHz mono; require duration > 5 giây.
2. Start **onefile đã package**, env token cố định cho test, test model enabled,
   `--port 0 --no-browser`; parse READY, health exact.
3. POST local endpoint với `tiny-test`, `punctuate=false`; chạy một lượt
   `diarize=false` để smoke nhanh và một native self-test riêng đã cover sherpa/ORT.
4. Poll job có timeout 10 phút, fail ngay nếu status error; export TXT, require HTTP 200,
   file > 0 byte và có ít nhất một sentence.
5. Shutdown authenticated, require process exit <= 5 giây và port đóng. Lặp offline bằng
   cache đã tải trong runtime container `--network none`.

### 5.2 Tauri headless smoke dưới Xvfb, tự động

1. Chạy release executable qua `xvfb-run -a`; Tauri mirror READY để script poll health.
2. `xdotool search --name '^ViTranscript$'` thấy đúng một window trong 60 giây.
3. Gửi window close; require Tauri exit, sidecar port đóng và không còn process group.
4. Smoke `.deb` sau install vào test VM/container có systemd không bắt buộc; AppImage dùng
   mode phù hợp môi trường (`--appimage-extract-and-run` nếu FUSE không có).

### 5.3 Ubuntu interactive, thủ công nhưng đo được

- AppImage double-click mở window không terminal/browser ngoài.
- `.deb` cài, menu launcher mở app.
- Picker native, menu, 2-file drop queue, local job, export, close/shutdown đều pass.
- Log không chứa token; network listener chỉ `127.0.0.1`; request thứ hai khi job chạy
  nhận 409; data nằm dưới `~/.local/share/ViTranscript`.
- Ghi phiên bản Ubuntu/WebKit, artifact SHA, checklist PASS/FAIL và screenshot. Các thao
  tác menu/dialog/drag-drop **không được tuyên bố pass chỉ từ Xvfb**.

## Task 6 — Docs dev/user và notices

- **Dev docs:** architecture/process tree, CLI/env/READY contracts, PyInstaller hook
  matrix, ffmpeg provenance, Ubuntu 22.04 build baseline, prereq WebKitGTK, target-triple
  naming, scripts/CI, log path, debug timeout/health/shutdown.
- **User docs:** `.AppImage` executable bit, `.deb` install/uninstall, `.dmg`/NSIS ở trạng
  thái chờ verify; lần tải model đầu; offline; picker/drop queue; close là thoát; data/log
  path; artifact chưa ký và cách vượt Gatekeeper/SmartScreen.
- README bỏ mô tả browser tự mở cho luồng desktop nhưng giữ hướng dẫn legacy scripts;
  phân biệt rõ desktop artifact và server legacy.
- `THIRD_PARTY_NOTICES.md` có ffmpeg build/version/license/source và các native runtime
  được phân phối. Không bundle model weights.

**Verify:** mọi command/path trong docs khớp script/config thực tế; link nội bộ không gãy;
không viết rằng tray, signing, update hoặc Mac/Win native verify đã có.

## Task 7 — Ma trận nghiệm thu và handoff

1. Điền DT-01..DT-11 bằng artifact hash/log/test cụ thể. Sau quyết định bỏ tray, DT-05 là
   “menu/dialog/drag-drop/queue”; tray không còn là tiêu chí.
2. Ubuntu chỉ PASS khi cả headless sidecar E2E, Xvfb shell smoke, artifact build và
   interactive checklist đạt. Nếu thiếu desktop session, DT-05 giữ PARTIAL/BLOCKED.
3. Mac arm64, Mac Intel, Windows x64 ghi riêng `CI BUILD PASS` nếu có log; native runtime
   vẫn `CHỜ VERIFY MÁY THẬT`.
4. Cập nhật `docs/03-tasks.md`, auto-update block `CLAUDE.md`, status block `AGENTS.md`
   đồng bộ khi task/status/module/script/test thay đổi; cập nhật danh sách file mới.
5. Chạy final gates:

```bash
uv run ruff check .
uv run pytest tests/ -v
cargo test --manifest-path desktop/src-tauri/Cargo.toml
desktop/scripts/build-linux.sh
scripts/e2e_sidecar_linux.py --sidecar <onefile-path>
scripts/smoke_desktop_linux.sh <release-or-appimage-path>
```

6. Review diff không có model/cache/secret/generated build dir. Commit theo task với trailer;
   push/tạo PR chỉ khi người điều phối yêu cầu.

## Thứ tự và phụ thuộc bắt buộc

```text
Task 0 backend contract
  └─> Task 1 PyInstaller spike (BLOCKER)
        └─> Task 2 Tauri lifecycle
              └─> Task 3 native bridge/UI
                    └─> Task 4 build + CI
                          └─> Task 5 Ubuntu E2E
                                └─> Task 6 docs
                                      └─> Task 7 acceptance
```

- Task 1 không thể đứng trước Task 0 vì binary cần `/healthz`, READY, shutdown contract để
  có gate thật; “spike làm trước” nghĩa là trước khi đầu tư Tauri shell.
- Task 2 chỉ bắt đầu sau onefile clean-runtime pass.
- Task 4 có thể scaffold icon/config sau Task 2, nhưng không được gọi artifact hoàn chỉnh
  trước native bridge Task 3.
- Docs có thể viết dần, nhưng số liệu artifact/checksum/acceptance chỉ điền sau Task 5.

## Rủi ro còn tồn đọng sau khi finalize plan

| Rủi ro | Cách gate / trạng thái |
|---|---|
| Native wheel/PyInstaller khác nhau theo OS | Ubuntu gate vòng này; Mac/Win CI build + máy thật sau |
| Onefile startup/antivirus và process tree Windows | Deadline/log + Job Object; vẫn cần Windows thật |
| ffmpeg binary license/provenance | Task 1 là gate distribution, cập nhật notices |
| AppImage phụ thuộc glibc/WebKit host | Build Ubuntu 22.04 + test 22.04 và host 26.04 |
| Remote Tauri capability cho dynamic loopback URL | Chỉ hai custom commands, no shell/fs, exact loopback URL |
| Symlink TOCTOU bởi local process cùng quyền | Chấp nhận v1, token per-instance + component validation |
| Menu/dialog/drag-drop không verify đủ bằng headless | Checklist interactive Ubuntu bắt buộc |
| macOS/Windows native behavior chưa verify | Không đánh dấu PASS; giữ blocker nghiệm thu riêng |

## Tham chiếu implementation

- Tauri v2 external binary và target triple:
  <https://v2.tauri.app/develop/sidecar/>
- Tauri v2 Linux prerequisites:
  <https://v2.tauri.app/start/prerequisites/>
- Tauri AppImage/glibc baseline:
  <https://v2.tauri.app/distribute/appimage/>
- Tauri remote capabilities:
  <https://v2.tauri.app/security/capabilities/>
- PyInstaller spec/`Analysis`/binaries:
  <https://pyinstaller.org/en/latest/spec-files.html>
