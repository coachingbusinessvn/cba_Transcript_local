# ViTranscript Desktop Shell v1.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Planning status (2026-07-19):** plan complete; no implementation step has been
> executed. Every unchecked box is intentional.

**Goal:** Sau khi Task 14 của v1 hoàn tất, đóng gói ViTranscript thành trải nghiệm desktop một chạm trên macOS và Windows: cài đặt bằng double-click, chạy ẩn qua browser, có tray/menu-bar để mở giao diện hoặc thoát, và gỡ sạch cả model đã tải.

**Architecture:** Giữ nguyên FastAPI + HTML tĩnh + `python -m app.server` và bind `127.0.0.1`. Thêm `app/runtime.py` để claim một instance bằng `server-state.json`, `app/tray.py` dùng lazy `pystray`, và file logging trong data dir; trên macOS/Windows, tray chạy ở main thread còn uvicorn chạy trong thread phụ. Installer macOS sinh `ViTranscript.app` thủ công; installer Windows tạo shortcut tới VBS wrapper chạy `.venv\\Scripts\\pythonw.exe` không hiện console.

**Tech Stack:** Python 3.12 qua `uv`, FastAPI/uvicorn, `pystray`, Pillow, shell script macOS, batch + PowerShell + VBScript Windows, pytest, ruff. Không thêm PyTorch, TensorFlow, PyInstaller, DMG hay Inno Setup.

**Spec:** [../../09-spec-desktop-shell.md](../../09-spec-desktop-shell.md)

**Task tracker:** [../../10-tasks-desktop-shell.md](../../10-tasks-desktop-shell.md)

---

## Preconditions and global constraints

- Chỉ bắt đầu thực hiện plan sau khi Task 14 nghiệm thu v1 đã hoàn tất hoặc người dùng xác nhận cho phép làm vỏ desktop trước; plan này không thay đổi tiêu chí core của v1.
- Mọi lệnh code chạy từ `.worktrees/vitranscript-impl/`.
- Không ghi dữ liệu model, job, settings, glossary hoặc log vào thư mục cài đặt; data vẫn nằm ở `config.data_dir()`.
- Server luôn bind `127.0.0.1`; chỉ port động từ `_free_port()` được truyền sang browser và tray.
- `.bat` và mọi chuỗi hiển thị trong `.bat` chỉ dùng ASCII không dấu. README, PowerShell, VBS và Python có thể dùng tiếng Việt.
- Giữ nguyên URL diarization có typo `speaker-recongition-models` nếu code liên quan được chạm tới; không sửa các thay đổi dở dang trong worktree hiện tại.
- Không dùng `rm -rf` với đường dẫn chưa kiểm tra. Uninstaller chỉ xóa các target tuyệt đối đã dựng từ `data_dir`, `.venv` của chính thư mục script, app bundle hoặc shortcut có tên chính xác.
- Mỗi task sau khi thực hiện: `uv run ruff check .`, verify riêng của task, rồi commit với trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- “v1.5” là tên milestone, không tự động đổi package version hay tạo/move git tag.
- Một user profile chỉ có một server instance. Lần mở app thứ hai phải mở URL của instance cũ rồi thoát, không tạo port/tray thứ hai.
- Daily launcher dùng Python trong `.venv` bằng đường dẫn tuyệt đối; `uv` chỉ bắt buộc trong install/update/dev flow.
- `pystray` phải được lazy-import để import/test headless không khởi tạo GUI backend.

## File map

### Planning artifacts already complete

- `docs/09-spec-desktop-shell.md` — spec chuẩn, acceptance IDs DS-01..DS-16.
- `docs/10-tasks-desktop-shell.md` — tracker implementation và bằng chứng từng nền tảng.
- `docs/dev/plans/2026-07-19-desktop-shell.md` — plan này.

### Files to create

- `app/tray.py` — adapter pystray, menu tiếng Việt, callback mở URL và shutdown.
- `app/runtime.py` — runtime state, exclusive single-instance claim, stale recovery và cleanup có ownership.
- `tests/test_desktop.py` — unit tests cho tray callback, runtime ownership/single-instance, logging và shutdown contract.
- `tests/test_uninstall_macos.sh` — destructive-safety fixture chạy hoàn toàn trong temp HOME.
- `assets/icon.png` — nguồn icon 1024x1024.
- `assets/icon.ico` — icon Windows dùng bởi shortcut.
- `assets/icon.icns` — icon macOS dùng bởi bundle.
- `scripts/build_icons.py` — tạo PNG/ICO và iconset để `iconutil` tạo ICNS.
- `scripts/launch-hidden.vbs` — chạy `pythonw.exe -m app.server` với working directory là thư mục cài.
- `scripts/create-shortcuts.ps1` — tạo shortcut Desktop và Start Menu.
- `scripts/uninstall-windows.ps1` — phần xử lý xác nhận, dừng process và xóa target Windows.
- `uninstall.command` — entry point gỡ cài đặt macOS.
- `uninstall.bat` — entry point ASCII gọi PowerShell uninstaller.
- `docs/images/macos-gatekeeper-open.png` — bằng chứng hướng dẫn Finder Gatekeeper.
- `docs/images/macos-privacy-open-anyway.png` — bằng chứng hướng dẫn Privacy & Security.
- `docs/images/windows-smartscreen-more-info.png` — bằng chứng hướng dẫn SmartScreen.

### Files to modify

- `pyproject.toml` — thêm `pystray` và `Pillow` runtime dependencies.
- `app/config.py` — thêm `logs_dir()` và `server_state_path()`.
- `app/server.py` — chuyển từ `uvicorn.run()` trực tiếp sang `uvicorn.Server`, nối runtime state/log/tray shutdown; vẫn có chế độ không tray cho test/headless.
- `tests/test_core.py` — chỉ sửa nếu cần tách fixture dùng chung; không làm mất test đang có.
- `install.command` — cài dependency rồi sinh/copy bundle vào `/Applications/ViTranscript.app`.
- `install.bat` — cài dependency rồi gọi script tạo shortcut.
- `README.md` — hướng dẫn icon app, tray, Gatekeeper/SmartScreen bằng ảnh và uninstall.
- `scripts/smoke_e2e.py` — thêm tùy chọn smoke kiểm tra server/tray contract nếu việc mở process được đưa vào smoke.
- `docs/10-tasks-desktop-shell.md` — chỉ cập nhật trạng thái sau verify thật; không suy ra Windows PASS từ macOS.

## Task 1: Runtime state, single-instance, logging, tray, and server lifecycle

**Files:**

- Modify: `pyproject.toml`
- Modify: `app/config.py`
- Create: `app/runtime.py`
- Create: `app/tray.py`
- Modify: `app/server.py`
- Create: `tests/test_desktop.py`

- [ ] **Step 1: Add failing tests for runtime ownership and tray contracts**

Create `tests/test_desktop.py` with these tests before production code:

```python
import logging
import os

import pytest
from fastapi.testclient import TestClient


def test_runtime_paths_are_inside_data_dir(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert config.logs_dir() == tmp_path / "logs"
    assert config.server_state_path() == tmp_path / "server-state.json"
    assert config.logs_dir().is_dir()


def test_second_claim_returns_the_live_instance(monkeypatch, tmp_path):
    from app import config, runtime

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    first = runtime.claim_state(8756)
    monkeypatch.setattr(runtime, "_process_exists", lambda _pid: True)
    monkeypatch.setattr(runtime, "_probe_runtime", lambda _state, _timeout=3.0: True)

    with pytest.raises(runtime.ExistingInstance) as caught:
        runtime.claim_state(8757)

    assert caught.value.state.instance_id == first.instance_id
    assert caught.value.state.port == 8756


def test_stale_state_is_replaced(monkeypatch, tmp_path):
    from app import config, runtime

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    old = runtime.claim_state(8756)
    monkeypatch.setattr(runtime, "_process_exists", lambda _pid: False)
    new = runtime.claim_state(8757)

    assert new.instance_id != old.instance_id
    assert runtime.load_state() == new


def test_release_only_removes_state_owned_by_the_instance(monkeypatch, tmp_path):
    from app import config, runtime

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    state = runtime.claim_state(8756)
    runtime.release_state("instance-khac")
    assert config.server_state_path().exists()
    runtime.release_state(state.instance_id)
    assert not config.server_state_path().exists()


def test_runtime_endpoint_identifies_current_process(monkeypatch, tmp_path):
    from app import runtime, server

    state = runtime.RuntimeState(
        schema_version=1,
        app="ViTranscript",
        instance_id="abc123",
        pid=os.getpid(),
        port=8756,
        install_dir=str(tmp_path),
        started_at="2026-07-19T10:00:00+07:00",
    )
    monkeypatch.setattr(server, "_RUNTIME_STATE", state)
    payload = TestClient(server.app).get("/api/runtime").json()
    assert payload == {
        "app": "ViTranscript",
        "instance_id": "abc123",
        "pid": os.getpid(),
        "port": 8756,
    }


def test_tray_controller_opens_url_and_requests_shutdown(monkeypatch):
    from app.tray import TrayController

    opened = []
    stopped = []
    monkeypatch.setattr("app.tray.webbrowser.open", lambda url: opened.append(url))
    controller = TrayController(8765, lambda: stopped.append(True))
    controller.open_ui()
    controller.quit(None, None)
    assert opened == ["http://127.0.0.1:8765"]
    assert stopped == [True]


def test_server_keeps_no_tray_mode_available(monkeypatch):
    from app import server

    monkeypatch.setenv("VITRANSCRIPT_NO_TRAY", "1")
    assert server._tray_enabled() is False


def test_file_logging_is_idempotent(monkeypatch, tmp_path):
    from app import config, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        server._configure_file_logging()
        server._configure_file_logging()
        target = str(tmp_path / "logs" / "server.log")
        matching = [
            h for h in root.handlers
            if isinstance(h, logging.FileHandler) and h.baseFilename == target
        ]
        assert len(matching) == 1
    finally:
        root.handlers[:] = before
```

Run:

```bash
uv run pytest tests/test_desktop.py -q
```

Expected: collection/run fails because `logs_dir`, `server_state_path`,
`app.runtime`, `TrayController`, `_tray_enabled` and `_configure_file_logging` do not
exist. Do not continue until the failures are for those missing contracts.

- [ ] **Step 2: Add dependencies and runtime paths**

Add these runtime dependencies to `pyproject.toml`:

```toml
    "pillow>=10.0",
    "pystray>=0.19.5",
```

Add below `jobs_dir()` in `app/config.py`:

```python
def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def server_state_path() -> Path:
    return data_dir() / "server-state.json"
```

Run:

```bash
uv sync
if uv tree | rg -i '(^|[-_])(torch|tensorflow)([-_]|$)'; then exit 1; fi
```

Expected: `uv sync` succeeds; the dependency search prints no package.

- [ ] **Step 3: Implement exclusive runtime state**

Create `app/runtime.py` with this data model and the three named public functions:

```python
@dataclass(frozen=True)
class RuntimeState:
    schema_version: int
    app: str
    instance_id: str
    pid: int
    port: int
    install_dir: str
    started_at: str

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class ExistingInstance(RuntimeError):
    def __init__(self, state: RuntimeState):
        super().__init__(f"ViTranscript is already running at {state.url}")
        self.state = state
```

- `load_state() -> RuntimeState | None`: parse and validate current state; malformed
  or missing content returns `None`.
- `claim_state(port: int) -> RuntimeState`: exclusive claim; raises
  `ExistingInstance` for a verified live instance.
- `release_state(instance_id: str) -> None`: remove only state owned by that instance.

Implementation rules (all are covered by the Step 1 tests or the additional focused
tests added here):

1. Validate `schema_version == 1`, `app == "ViTranscript"`, non-empty instance ID,
   PID > 0, and port in `8756..8805`.
2. Build new state with `uuid.uuid4().hex`, `os.getpid()`, the chosen port,
   `Path(__file__).resolve().parent.parent`, and an ISO-8601 timezone-aware timestamp.
3. Claim with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`; write
   JSON, flush and `os.fsync` before closing.
4. On `FileExistsError`, load the existing state. If its PID exists, probe
   `<url>/api/runtime` for up to 3 seconds and require matching app, instance ID, PID
   and port. Raise `ExistingInstance(existing)` on a match.
5. A dead PID, invalid JSON, or a mismatched endpoint is stale. Remove it only after
   re-reading and proving the observed instance ID/file fingerprint is unchanged,
   then retry exclusive create once.
6. `_process_exists(pid)` uses `os.kill(pid, 0)` and treats `PermissionError` as
   “exists”; `_probe_runtime` uses `urllib.request` with loopback URL and bounded
   timeout only.
7. `release_state(instance_id)` re-reads the file and unlinks only when the current
   instance ID matches. Missing/foreign state is a no-op.

Add focused tests for invalid JSON, invalid port, probe mismatch and cleanup of a
foreign instance. Run:

```bash
uv run pytest tests/test_desktop.py -q
```

Expected: runtime tests pass; tray/server tests remain red.

- [ ] **Step 4: Implement the lazy tray adapter**

Create `app/tray.py` with this complete structure:

```python
"""System tray/menu-bar integration for the hidden desktop launcher."""
from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw


def _load_icon_image() -> Image.Image:
    path = Path(__file__).parent.parent / "assets" / "icon.png"
    if path.exists():
        with Image.open(path) as source:
            return source.convert("RGBA").copy()
    image = Image.new("RGBA", (64, 64), (36, 86, 160, 255))
    draw = ImageDraw.Draw(image)
    draw.line((12, 42, 24, 25, 34, 38, 50, 17), fill="white", width=6)
    return image


class TrayController:
    def __init__(self, port: int, request_shutdown: Callable[[], None]):
        self.url = f"http://127.0.0.1:{port}"
        self.request_shutdown = request_shutdown

    def open_ui(self, _icon: Any = None, _item: Any = None) -> None:
        webbrowser.open(self.url)

    def quit(self, icon: Any, _item: Any = None) -> None:
        self.request_shutdown()
        if icon is not None:
            icon.stop()

    def create_icon(self) -> Any:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("Mở giao diện", self.open_ui),
            pystray.MenuItem("Thoát", self.quit),
        )
        return pystray.Icon("vitranscript", _load_icon_image(), "ViTranscript", menu)
```

The local import of `pystray` is mandatory. Add a test that imports `app.tray` while
blocking import of `pystray`; importing the module must still succeed, while
`create_icon()` may fail as expected without the backend.

- [ ] **Step 5: Refactor server startup without touching job endpoints**

In `app/server.py`:

1. Import `os` and `.runtime`; do **not** import `.tray` at module scope.
2. Add module global `_RUNTIME_STATE: runtime.RuntimeState | None = None`.
3. Add `GET /api/runtime`; return only `app`, `instance_id`, `pid`, `port`, or HTTP
   503 when startup has not claimed state.
4. Add `_tray_enabled()`, `_configure_file_logging()`, `_wait_until_started()` and
   replace `main()`.

Use these lifecycle rules exactly:

```python
def _tray_enabled() -> bool:
    return os.environ.get("VITRANSCRIPT_NO_TRAY") != "1"


def _configure_file_logging() -> None:
    log_path = config.logs_dir() / "server.log"
    root = logging.getLogger()
    if any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in root.handlers
    ):
        return
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(handler)


def _wait_until_started(
    uvicorn_server: uvicorn.Server,
    server_thread: threading.Thread,
    timeout: float = 15.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if uvicorn_server.started:
            return True
        if not server_thread.is_alive():
            return False
        time.sleep(0.05)
    return False
```

`main()` order:

1. Configure file logging and choose port.
2. Call `runtime.claim_state(port)`. On `ExistingInstance`, call
   `webbrowser.open(existing.state.url)` and return 0 without creating tray/server.
3. Assign `_RUNTIME_STATE`, create
   `uvicorn.Config(app, host="127.0.0.1", port=state.port, log_level="info")`, then
   create `uvicorn.Server` from that config.
4. In no-tray mode, start a daemon opener thread that waits for `server.started`, then
   opens the browser; run uvicorn on the current thread.
5. In tray mode, run uvicorn in one non-daemon thread. Wait up to 15 seconds for
   `server.started`; on timeout/dead thread, raise a clear startup error and do not
   open the browser.
6. Only after ready, lazy-import `TrayController`, create the icon, open the browser,
   and run `icon.run()` on the main thread.
7. Start a daemon watcher that joins the uvicorn thread and calls `icon.stop()` if the
   server exits unexpectedly, so the tray cannot remain orphaned.
8. In tray `finally`, set `uvicorn_server.should_exit = True` and join for 15 seconds;
   log an error if the thread remains alive.
9. In outer `finally`, call `runtime.release_state(state.instance_id)` and clear
   `_RUNTIME_STATE`. Cleanup must also happen for Ctrl+C/startup error.

Do not change `_JOBS_LOCK`, `create_job`, export endpoints, `127.0.0.1`, port range,
or HTTP 409 behavior.

Add unit tests with fake `uvicorn.Server`, fake thread/icon and patched browser to
prove: browser waits for `started`, second invocation creates no server, tray quit
sets `should_exit`, unexpected server exit stops icon, and state cleanup runs on an
exception.

- [ ] **Step 6: Verify Task 1 and commit**

Run:

```bash
uv run pytest tests/test_desktop.py tests/test_core.py -v
uv run ruff check .
if uv tree | rg -i '(^|[-_])(torch|tensorflow)([-_]|$)'; then exit 1; fi
```

Expected: all tests pass, ruff is clean, and dependency scan prints no match.

```bash
git add pyproject.toml uv.lock app/config.py app/runtime.py app/tray.py app/server.py tests/test_desktop.py
git commit -m "feat: add single-instance tray lifecycle" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 2: Build shared icon assets and the macOS `.app` installer

**Files:**

- Create: `assets/icon.png`, `assets/icon.ico`, `assets/icon.icns`
- Create: `scripts/build_icons.py`
- Modify: `install.command`

- [ ] **Step 1: Create deterministic icon assets**

Create a 1024x1024 source icon with a transparent background, a rounded blue square, and a white `V`/waveform mark. Export the same mark to `assets/icon.png`, `assets/icon.ico`, and `assets/icon.icns`; do not use a platform-only icon.

Create `scripts/build_icons.py` with this deterministic generator:

```python
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "assets"
ICONSET = ROOT / "ViTranscript.iconset"
ICO_SIZES = [16, 32, 48, 64, 128, 256]
ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 12
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 6,
        fill=(36, 86, 160, 255),
    )
    points = [
        (size * 0.22, size * 0.38),
        (size * 0.36, size * 0.65),
        (size * 0.50, size * 0.48),
        (size * 0.64, size * 0.65),
        (size * 0.80, size * 0.32),
    ]
    draw.line(points, fill=(255, 255, 255, 255), width=max(2, size // 14), joint="curve")
    return image


ASSETS.mkdir(parents=True, exist_ok=True)
draw(1024).save(ASSETS / "icon.png")
draw(1024).save(ASSETS / "icon.ico", sizes=[(s, s) for s in ICO_SIZES])
if ICONSET.exists():
    shutil.rmtree(ICONSET)
ICONSET.mkdir()
for filename, size in ICONSET_FILES.items():
    draw(size).save(ICONSET / filename)
subprocess.run(["iconutil", "-c", "icns", "-o", str(ASSETS / "icon.icns"), str(ICONSET)], check=True)
shutil.rmtree(ICONSET)
```

Use the local Pillow environment to generate PNG/ICO and macOS `iconutil` to generate ICNS:

```bash
uv run python scripts/build_icons.py
test -s assets/icon.png
test -s assets/icon.ico
test -s assets/icon.icns
```

The implementation must write the exact ten standard iconset filenames shown above;
`iconutil` does not accept arbitrary names such as `icon_48x48.png`. Remove the
temporary iconset after a successful conversion; keep only the three release assets.

- [ ] **Step 2: Replace `install.command` with a bundle-producing installer**

Keep the install terminal visible because the first install downloads uv, Python, dependencies and models on demand. Replace the current script with a `set -euo pipefail` script that:

1. Resolves `INSTALL_DIR` using `cd "$(dirname "$0")"`.
2. Resolves uv to `$HOME/.local/bin/uv`, installing it only when that executable is absent.
3. Runs `uv python install 3.12` and `uv sync --directory "$INSTALL_DIR"`.
4. Creates `/Applications/ViTranscript.app/Contents/{MacOS,Resources}`.
5. Writes `Info.plist` with bundle id `com.vitranscript.app`, executable `launcher`, icon `icon.icns`, and `LSUIElement=true`.
6. Refuses update while a matching live instance in `server-state.json` is running;
   print “Thoát từ menu bar rồi chạy lại installer”. A stale state must not block
   install.
7. Writes an executable launcher with the install directory embedded as an absolute path. The launcher must run:

```bash
INSTALL_DIR="$INSTALL_DIR"
DATA_DIR="$HOME/Library/Application Support/ViTranscript"
LOG_FILE="$DATA_DIR/logs/launcher.log"
mkdir -p "$DATA_DIR/logs"
cd "$INSTALL_DIR"
nohup "$INSTALL_DIR/.venv/bin/python" -m app.server \
  >> "$LOG_FILE" 2>&1 < /dev/null &
```

The actual generated launcher must substitute the resolved `INSTALL_DIR`; it must not depend on the Finder-inherited `PATH`. Before writing it, verify `.venv/bin/python` exists. Copy `assets/icon.icns` into `Contents/Resources/icon.icns`, mark `Contents/MacOS/launcher` executable, and replace an existing `/Applications/ViTranscript.app` only after verifying the target is exactly that bundle path.

Finish with a Vietnamese terminal message explaining that daily use is now the Applications icon and that the extracted install folder must not be moved/deleted while the app is installed, then wait for one keypress. The script must not launch `run.command`.

- [ ] **Step 3: Verify macOS installer artifacts without starting a job**

Run:

```bash
bash -n install.command
rg -q 'ViTranscript\.app|Contents/MacOS/launcher|Contents/Resources/icon\.icns' install.command
chmod +x install.command
./install.command
/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" /Applications/ViTranscript.app/Contents/Info.plist
test -x /Applications/ViTranscript.app/Contents/MacOS/launcher
test -s /Applications/ViTranscript.app/Contents/Resources/icon.icns
rg -q '\.venv/bin/python.*-m app\.server' /Applications/ViTranscript.app/Contents/MacOS/launcher
! rg -q 'uv run' /Applications/ViTranscript.app/Contents/MacOS/launcher
```

Expected: bundle exists, executable is `launcher`, daily runtime uses the absolute
venv Python, and no model job has been run. Then verify a second installer run updates
the same exact bundle without deleting a sentinel file placed under the data/model
directory.

- [ ] **Step 4: Commit Task 2**

```bash
git add assets scripts/build_icons.py install.command
git commit -m "feat: create macos app bundle installer" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 3: Build the Windows hidden launcher and shortcuts

**Files:**

- Use: `assets/icon.ico` created by Task 2
- Create: `scripts/launch-hidden.vbs`
- Create: `scripts/create-shortcuts.ps1`
- Modify: `install.bat`

- [ ] **Step 1: Implement the VBS wrapper**

Create `scripts/launch-hidden.vbs` with ASCII-safe code that locates the install directory two levels above itself, sets it as the working directory, and runs the venv interpreter hidden:

```vbscript
Option Explicit

Dim fso, shell, installDir, pythonw
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
installDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonw = installDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    MsgBox "ViTranscript is not installed correctly. Run install.bat again.", 16, "ViTranscript"
    WScript.Quit 1
End If
shell.CurrentDirectory = installDir
shell.Run """" & pythonw & """ -m app.server", 0, False
```

The wrapper must not call `uv` at daily runtime. Installation already created `.venv`, and direct `pythonw.exe` avoids both console creation and a dependency on PATH. It must be ASCII-only so Windows Script Host can read it consistently on non-UTF-8 codepages.

- [ ] **Step 2: Implement shortcut creation**

Create `scripts/create-shortcuts.ps1` with a mandatory `-InstallDir` parameter. It must resolve the source path and create both links with `WScript.Shell`:

```powershell
param([Parameter(Mandatory = $true)][string] $InstallDir)
$ErrorActionPreference = "Stop"
$InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
$vbs = Join-Path $InstallDir "scripts\launch-hidden.vbs"
$icon = Join-Path $InstallDir "assets\icon.ico"
$target = Join-Path $env:WINDIR "System32\wscript.exe"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$desktop = [Environment]::GetFolderPath("Desktop")

function New-ViTranscriptShortcut([string] $Path) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath = $target
    $link.Arguments = "//nologo `"$vbs`""
    $link.WorkingDirectory = $InstallDir
    $link.IconLocation = "$icon,0"
    $link.Description = "ViTranscript"
    $link.Save()
}

New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
New-ViTranscriptShortcut (Join-Path $desktop "ViTranscript.lnk")
New-ViTranscriptShortcut (Join-Path $startMenu "ViTranscript.lnk")
```

- [ ] **Step 3: Update `install.bat`**

Keep every line ASCII-only. The script must resolve `%~dp0`, install uv if missing, add `%USERPROFILE%\.local\bin` to the current process PATH, run `uv python install 3.12`, run `uv sync`, verify `.venv\Scripts\pythonw.exe` and `assets\icon.ico`, then invoke:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-shortcuts.ps1" -InstallDir "%~dp0"
```

Before changing runtime files, use PowerShell to inspect `%APPDATA%\ViTranscript\server-state.json`; if `GET /api/runtime` confirms the matching live instance, stop with an ASCII message asking the user to choose tray `Thoát` and rerun install. Invalid/stale state does not block update.

It must end with `pause`, say that the Desktop shortcut is ready, warn that the extracted install folder must not be moved/deleted, and never start `run.bat`. Keep `run.bat` as a visible-console developer/debug entry point.

- [ ] **Step 4: Verify Windows artifacts and fallback**

On a real Windows x64 machine:

```bat
install.bat
```

Verify:

- `Desktop\ViTranscript.lnk` and `%APPDATA%\Microsoft\Windows\Start Menu\Programs\ViTranscript.lnk` exist.
- Shortcut target is `wscript.exe`, its argument contains `scripts\launch-hidden.vbs`, and its icon is `assets\icon.ico`.
- Double-click creates no console window and opens a browser URL in the 8756+ range.
- Double-click a second time: browser opens the same port and the original PID remains the only server PID.
- If an antivirus blocks VBS, edit the shortcut target to `%~dp0.venv\Scripts\pythonw.exe` with argument `-m app.server` and working directory set to the install directory; document this exact fallback in README.

On macOS or CI, run only the static checks:

```bash
uv run python -c 'from pathlib import Path; p=Path("install.bat").read_bytes(); assert all(b < 128 for b in p)'
uv run python -c 'from pathlib import Path; p=Path("scripts/launch-hidden.vbs").read_bytes(); assert all(b < 128 for b in p)'
test -s assets/icon.ico
```

- [ ] **Step 5: Commit Task 3**

Commit:

```bash
git add install.bat scripts/launch-hidden.vbs scripts/create-shortcuts.ps1 assets/icon.ico
git commit -m "feat: add hidden windows launcher and shortcuts" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 4: Implement clean uninstallers with two confirmations

**Files:**

- Create: `uninstall.command`
- Create: `uninstall.bat`
- Create: `scripts/uninstall-windows.ps1`

- [ ] **Step 1: Write failing safety tests for the macOS uninstaller**

Create `tests/test_uninstall_macos.sh`. The test must copy `uninstall.command` into a
temporary install directory, set a temporary `HOME`, create fake data/model, fake
`.venv`, and override the app target through a test-only
`VITRANSCRIPT_APP_PATH` environment variable that is honored only when
`VITRANSCRIPT_UNINSTALL_TEST=1`.

The test covers four isolated cases:

1. first prompt `N`: every target remains;
2. first `Y`, second `N`: fake data/app/venv disappear; fake uv remains;
3. first `Y`, second `Y`: only the fake, explicitly returned uv paths disappear;
4. foreign/mismatched runtime endpoint: no PID is killed and uninstall exits with a
   message asking the user to quit from tray.

Run `bash tests/test_uninstall_macos.sh`. Expected: FAIL because the uninstaller and
test hooks do not exist.

- [ ] **Step 2: Implement macOS uninstaller**

`uninstall.command` must resolve these exact targets:

```bash
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$HOME/Library/Application Support/ViTranscript"
APP_PATH="/Applications/ViTranscript.app"
VENV_PATH="$INSTALL_DIR/.venv"
STATE_FILE="$DATA_DIR/server-state.json"
```

The script must:

1. Parse `server-state.json`; require app name, instance ID, numeric PID and loopback
   port. A missing/dead PID is stale and needs no kill. For a live PID, probe
   `/api/runtime` and require all values to match before sending `TERM`. Wait up to 10
   seconds; if it remains alive, send `KILL` only to that validated PID. If a live PID
   cannot be identified, do not kill and ask the user to quit from tray.
2. Print the data size using `du -sh -- "$DATA_DIR"` when the directory exists.
3. Ask once: `Xoa ViTranscript data, app va .venv? [y/N]`. Any answer other than `y`/`Y` exits without deletion.
4. After confirmation, remove only `$DATA_DIR`, `$APP_PATH`, and `$VENV_PATH` after checking each path is non-empty and has the expected final component (`ViTranscript`, `ViTranscript.app`, `.venv`).
5. Before deleting uv, resolve the uv executable and capture `uv python dir`. Ask a
   second optional question: `Xoa uv va Python do uv quan ly? Cong cu nay co the dang
   duoc app khac su dung. [y/N]`. Default is keep. On `y`/`Y`, remove only the resolved
   `uv`, sibling `uvx`, and the exact absolute directory returned by `uv python dir`.
   If the directory cannot be verified as inside the current user's home, keep it.
6. Say that the source folder itself is intentionally not deleted; the user should move it to Trash after the script exits.

- [ ] **Step 3: Implement Windows uninstaller**

`uninstall.bat` remains ASCII-only and calls:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall-windows.ps1" -InstallDir "%~dp0"
```

`scripts/uninstall-windows.ps1` must:

- Resolve `$dataDir = Join-Path $env:APPDATA "ViTranscript"` and `$venv = Join-Path $InstallDir ".venv"`.
- Read `$dataDir\server-state.json`; a missing/dead PID is stale and needs no kill.
  For a live PID, call loopback `/api/runtime` and require matching app, instance ID,
  PID and port. Only then call `Stop-Process`/`taskkill` for that exact PID. If a live
  PID cannot be identified, preserve it and ask the user to quit from tray.
- Calculate and print model/data size with `Get-ChildItem -LiteralPath $dataDir -Recurse -File | Measure-Object -Property Length -Sum`.
- Ask the first confirmation before deleting `$dataDir`, the exact Desktop shortcut, the exact Start Menu shortcut, and `$venv`.
- Ask the second confirmation with a shared-tool warning before deleting the resolved
  uv executable(s) and the uv-managed Python directory returned by `uv python dir`
  before uv is removed. If `uv python dir` is unavailable or outside the current user
  profile, print the path and keep it rather than deleting an unverified directory.
- Explain that the install source folder is not removed automatically.

- [ ] **Step 4: Test destructive behavior in temporary fixtures**

Do not test against the real home data directory. On macOS, use the test from Step 1.
On Windows, use a disposable local user profile or VM snapshot with the same four
cases. Verify every `N` path leaves targets intact and every `Y` path removes exactly
the allowlisted targets. Save the printed deletion list as acceptance evidence.

Run after implementation:

```bash
bash -n uninstall.command
bash tests/test_uninstall_macos.sh
uv run ruff check .
```

- [ ] **Step 5: Commit Task 4**

Commit:

```bash
git add uninstall.command uninstall.bat scripts/uninstall-windows.ps1
git commit -m "feat: add clean uninstallers" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 5: Update README and add desktop acceptance smoke checks

**Files:**

- Modify: `README.md`
- Modify: `scripts/smoke_e2e.py` only if the server lifecycle check is added there
- Create: `docs/images/macos-gatekeeper-open.png`, `docs/images/macos-privacy-open-anyway.png`, `docs/images/windows-smartscreen-more-info.png`

- [ ] **Step 1: Update the user flow**

Change the README so the primary flow is:

1. Download zip and extract it.
2. Double-click `install.command` or `install.bat` once.
3. Open `ViTranscript.app` from Applications or the `ViTranscript` shortcut from Desktop/Start Menu.
4. Use the browser UI; close/reopen the tab through tray `Mở giao diện`.
5. Stop from tray `Thoát`.

Keep `run.command` and `run.bat` documented as developer/debug fallback, not the normal daily flow.

Add a prominent note immediately after install: the extracted folder is the install
folder because it contains code and `.venv`; do not move/delete it before uninstall.
Explain that launching the icon twice reuses the current instance and opens the same
browser URL.

- [ ] **Step 2: Add warning screenshots and exact instructions**

Add screenshots with Vietnamese captions and alt text:

- macOS Finder: right-click `install.command` → `Open` → `Open`.
- macOS newer versions: System Settings → Privacy & Security → `Open Anyway`.
- Windows SmartScreen: `More info` → `Run anyway`.

The screenshots must be captured from the supported OS versions and committed at the exact paths above. Captions record the OS/version used. Do not claim the app is signed or notarized and do not instruct users to disable Gatekeeper or SmartScreen globally.

- [ ] **Step 3: Add uninstall and troubleshooting sections**

Document:

- First uninstall confirmation removes data/model, app or shortcuts, and `.venv`.
- Second optional confirmation removes shared uv and uv-managed Python; default is keep.
- The install source folder remains and can be moved to Trash manually.
- Manual data paths: `~/Library/Application Support/ViTranscript` and `%APPDATA%\\ViTranscript`.
- VBS antivirus fallback: shortcut target `.venv\\Scripts\\pythonw.exe`, argument `-m app.server`, working directory install folder.
- Server log path: `<data_dir>/logs/server.log`.
- macOS launcher bootstrap log: `<data_dir>/logs/launcher.log`.
- `server-state.json` is runtime metadata, not a user job; stale state is recovered
  automatically on next valid launch.
- Closing the browser tab does not stop the tray process.
- If update says the app is running, use tray `Thoát` and rerun installer; never delete
  `.venv` while a transcription job is active.

- [ ] **Step 4: Verify docs and acceptance behavior**

Run:

```bash
uv run ruff check .
uv run pytest tests/ -v
uv run python -c 'from pathlib import Path; text=Path("README.md").read_text(encoding="utf-8"); assert "Gỡ cài đặt" in text; assert "server.log" in text; assert "Open Anyway" in text'
```

On macOS, execute the real acceptance sequence:

```bash
./install.command
open /Applications/ViTranscript.app
PORT=$(rg -o '127\\.0\\.0\\.1:[0-9]+' "$HOME/Library/Application Support/ViTranscript/logs/server.log" | tail -1 | cut -d: -f2)
curl --fail "http://127.0.0.1:$PORT/"
ps ax | rg '[p]ython.*-m app.server'
```

Launch the Applications icon a second time and verify PID/port do not change. Then
close the browser tab, click tray `Mở giao diện`, click tray `Thoát`, and verify the
matching PID and `server-state.json` disappear.

The real uninstall/reinstall sequence is destructive. Run it only on a disposable
acceptance user profile/machine with no valuable model/job data. Run
`./uninstall.command`, confirm both prompts, verify data/app/venv are absent, then run
`./install.command` again and confirm reinstall creates the app bundle.

On Windows, repeat the same sequence with Desktop shortcut, Task Manager, tray menu, `uninstall.bat`, and a reinstall. Record Windows results separately because they cannot be inferred from macOS.

Do not claim the acceptance criteria pass until both real-platform sequences have been observed. Commit docs only after the screenshots and manual results are available:

- [ ] **Step 5: Commit Task 5**

```bash
git add README.md docs/images scripts/smoke_e2e.py
git commit -m "docs: document desktop install and uninstall flow" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 6: Final verification and project status update

**Files:**

- Modify: `docs/10-tasks-desktop-shell.md`
- Modify: `docs/03-tasks.md` only to add a cross-link after desktop acceptance is real
- Optionally modify: `README.md` if a verified command or platform result needs correction

- [ ] **Step 1: Run all automated verification from a clean implementation state**

Run the complete local checks:

```bash
uv run ruff check .
uv run pytest tests/ -v
bash -n install.command uninstall.command
bash tests/test_uninstall_macos.sh
uv run python -c 'from pathlib import Path; paths=[Path("install.bat"),Path("uninstall.bat"),Path("scripts/launch-hidden.vbs")]; assert all(all(b < 128 for b in p.read_bytes()) for p in paths)'
test -s assets/icon.png
test -s assets/icon.ico
test -s assets/icon.icns
if uv tree | rg -i '(^|[-_])(torch|tensorflow)([-_]|$)'; then exit 1; fi
```

Run the existing core smoke test after the server lifecycle change:

```bash
uv run python scripts/smoke_e2e.py
```

- [ ] **Step 2: Audit every spec criterion**

Confirm explicitly:

- core server still uses `127.0.0.1` and HTTP 409 single-job behavior;
- pystray menu has exactly `Mở giao diện` and `Thoát`;
- browser close leaves process alive;
- tray `Thoát` makes the server process terminate;
- uninstall removes model data and `.venv` after the first confirmation;
- optional second confirmation removes only explicitly approved uv/Python targets;
- reinstall succeeds immediately after uninstall;
- no `.bat` contains non-ASCII bytes;
- no PyTorch or TensorFlow dependency was introduced.
- second launch reuses the original PID/port and creates no second tray;
- `/api/runtime` exposes only app/instance/PID/port;
- stale/foreign runtime state cannot delete another instance's state or kill an
  unrelated PID;
- app/server/launcher logs contain no transcript or glossary text.

Map evidence line-by-line to DS-01..DS-16 in
`docs/10-tasks-desktop-shell.md`. Use `PASS`, `FAIL`, `BLOCKED` or `—`; never use a
Mac result as Windows evidence.

- [ ] **Step 3: Update task status without creating a release tag**

Only after checks, update `docs/10-tasks-desktop-shell.md` with platform-specific
evidence. Add a cross-link from `docs/03-tasks.md` only when useful; do not merge v1.5
acceptance into core Task 14. Do not create or move `v0.1.0` (or any other tag) unless
the user explicitly authorizes release after all required acceptance is complete.

- [ ] **Step 4: Commit verification evidence**

```bash
git add docs/10-tasks-desktop-shell.md docs/03-tasks.md README.md
git commit -m "docs: record desktop shell acceptance" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Self-review against `docs/09-spec-desktop-shell.md`

- Manual macOS bundle with `Info.plist`, `Contents/MacOS/launcher`, and `Resources/icon.icns`: Task 2.
- Launcher embeds install path, resolves absolute `.venv` Python, uses `nohup`, and writes bootstrap/app logs: Task 2 plus Task 1 logging.
- Windows Desktop + Start Menu shortcuts, icon, hidden VBS wrapper, and direct `pythonw.exe` fallback: Task 3.
- Tray/menu-bar with exact two menu items and macOS main-thread constraint: Task 1.
- Clean uninstall, model deletion, `.venv` deletion, optional uv/Python deletion and two confirmations: Task 4.
- README Gatekeeper/SmartScreen screenshots and troubleshooting data paths: Task 5.
- Browser close/reopen, real process termination, reinstall-after-uninstall, and platform evidence: Task 5 and Task 6.
- Exclusive single-instance, `/api/runtime`, stale recovery and owned cleanup: Task 1.
- Safe PID validation before uninstall: Task 4.
- Explicit out-of-scope items (PyInstaller, DMG, Inno Setup, signing/notarization, auto-update, native window) remain excluded from every task.

### Acceptance traceability

| Spec IDs | Plan coverage |
|---|---|
| DS-01, DS-02, DS-03 | Task 2 (Mac), Task 3 (Windows), Task 5/6 (real evidence) |
| DS-04, DS-05 | Task 1 lifecycle tests, Task 5/6 real launch |
| DS-06 | Task 1 exclusive state + Task 3/5 second-launch checks |
| DS-07, DS-08 | Task 1 tray/shutdown + Task 5/6 real evidence |
| DS-09 | Task 1 regression guard + Task 6 core smoke |
| DS-10 | Task 1 logging tests + Task 5 docs + Task 6 audit |
| DS-11, DS-12, DS-13 | Task 4 fixtures and platform uninstall runs |
| DS-14 | Task 5 destructive disposable-profile acceptance |
| DS-15 | Task 1 dependency scan, Task 3 ASCII checks, Task 6 final scan |
| DS-16 | Task 5 versioned screenshots and README review |

Coverage mapping is recorded in the spec traceability table. The only verification
that cannot be completed on the current macOS-only development environment is the
real Windows shortcut/tray/uninstall sequence; it must be recorded as `BLOCKED` or
unverified rather than inferred.
