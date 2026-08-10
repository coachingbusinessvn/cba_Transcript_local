"""Runtime desktop sidecar: CLI, bind socket, READY, auth helpers, path validate, self-test.

Tách khỏi FastAPI app để test được độc lập và giữ `python -m app.server` ổn định.
"""
from __future__ import annotations

import argparse
import hmac
import importlib
import ipaddress
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

# Dải port dynamic (inclusive): 8756..8805
PORT_RANGE_START = 8756
PORT_RANGE_END = 8805

READY_LINE_RE = re.compile(r"^VITRANSCRIPT_READY http://127\.0\.0\.1:(\d+)$")
INSTANCE_TOKEN_ENV = "VITRANSCRIPT_INSTANCE_TOKEN"
TEST_MODEL_ENV = "VITRANSCRIPT_ENABLE_TEST_MODEL"
TOKEN_HEADER = "X-ViTranscript-Token"

_NATIVE_PACKAGES = (
    "ctranslate2",
    "onnxruntime",
    "sherpa_onnx",
    "tokenizers",
    "faster_whisper",
    "av",
    "static_ffmpeg",
)


def port_arg(value: str) -> int:
    try:
        v = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"port phải là số nguyên, nhận: {value!r}") from e
    if v < 0 or v > 65535:
        raise argparse.ArgumentTypeError(f"port phải trong 0..65535, nhận: {v}")
    return v


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vitranscript-sidecar", description="ViTranscript server")
    p.add_argument(
        "--port",
        type=port_arg,
        default=0,
        help="Port cố định; 0 = chọn tự động trong 8756..8805 (mặc định)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Không mở browser (desktop sidecar)",
    )
    p.add_argument(
        "--self-test-native",
        action="store_true",
        help="Import native packages + ffmpeg/ffprobe -version rồi thoát",
    )
    return p


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def format_ready_line(port: int) -> str:
    return f"VITRANSCRIPT_READY http://127.0.0.1:{port}"


def bind_server_socket(port: int = 0) -> tuple[socket.socket, int]:
    """Bind 127.0.0.1 và giữ socket (truyền cho Uvicorn) — không TOCTOU check-then-bind.

    port=0: thử lần lượt 8756..8805.
    port cố định: bind đúng port hoặc raise RuntimeError.
    """
    if port == 0:
        candidates = list(range(PORT_RANGE_START, PORT_RANGE_END + 1))
    else:
        candidates = [port]

    last_err: OSError | None = None
    for p in candidates:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Không SO_REUSEADDR trên Windows cho fixed port occupied detection
            # nhưng trên Linux REUSEADDR giúp restart nhanh; fixed occupied vẫn fail
            # nếu process khác đang LISTEN.
            if port == 0:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", p))
            sock.listen(2048)
            actual = sock.getsockname()[1]
            return sock, actual
        except OSError as e:
            last_err = e
            try:
                sock.close()
            except OSError:
                pass
    if port == 0:
        raise RuntimeError(
            f"Không bind được port trống trong {PORT_RANGE_START}..{PORT_RANGE_END}: {last_err}"
        )
    raise RuntimeError(f"Port {port} đã bị chiếm hoặc không bind được: {last_err}")


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def tokens_match(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    # hmac.compare_digest yêu cầu cùng kiểu/độ dài tương đương — encode utf-8
    a = expected.encode("utf-8")
    b = provided.encode("utf-8")
    if len(a) != len(b):
        # Vẫn so sánh với padding giả để giảm leak độ dài? Plan yêu cầu constant-time
        # cho token đúng format; độ dài khác → False ngay (token fixed length 256-bit hex).
        return False
    return hmac.compare_digest(a, b)


def configured_instance_token() -> str | None:
    val = os.environ.get(INSTANCE_TOKEN_ENV)
    if val is None or val == "":
        return None
    return val


def maybe_register_test_model() -> None:
    """Đăng ký key tiny-test → source tiny chỉ khi env test bật."""
    from . import config

    if os.environ.get(TEST_MODEL_ENV) == "1":
        config.MODEL_REGISTRY.setdefault(
            "tiny-test",
            {
                "source": "tiny",
                "label": "Tiny (test only — không hiện cho user)",
                "size": "~75 MB",
            },
        )


def _is_windows_reparse(path: Path) -> bool:
    """True nếu path là reparse point (junction/symlink) trên Windows.

    Dùng ctypes GetFileAttributesW; trên non-Windows luôn False.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore[attr-defined]
        if attrs == -1:
            return False
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


def validate_local_media_path(path_str: str) -> Path:
    """Validate absolute local media path theo thứ tự plan (reject symlink/reparse).

    Raises ValueError với message tiếng Việt ngắn gọn.
    """
    from . import media

    if not isinstance(path_str, str) or path_str == "":
        raise ValueError("path phải là chuỗi không rỗng")
    if "\x00" in path_str:
        raise ValueError("path không được chứa ký tự NUL")

    p = Path(path_str)
    if not p.is_absolute():
        raise ValueError("path phải là đường dẫn tuyệt đối (absolute)")

    # Reject mọi component '..' trước resolve
    if ".." in p.parts:
        raise ValueError("path không được chứa component '..'")

    # lstat từng component từ anchor tới file — reject symlink
    # Xây dựng dần từ root
    parts = p.parts
    if sys.platform == "win32":
        # parts[0] là drive root như 'C:\\'
        cur = Path(parts[0])
        rest = parts[1:]
    else:
        cur = Path(parts[0])  # '/'
        rest = parts[1:]

    for part in rest:
        cur = cur / part
        try:
            st = cur.lstat()
        except OSError as e:
            raise ValueError(f"Đường dẫn không tồn tại: {cur.name}") from e
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"Không chấp nhận symlink: {cur.name}")
        if sys.platform == "win32" and _is_windows_reparse(cur):
            raise ValueError(f"Không chấp nhận reparse/junction: {cur.name}")

    try:
        resolved = p.resolve(strict=True)
    except (OSError, FileNotFoundError) as e:
        raise ValueError("Đường dẫn không tồn tại") from e

    try:
        st = resolved.stat()
    except OSError as e:
        raise ValueError("Không đọc được file") from e

    if not stat.S_ISREG(st.st_mode):
        if stat.S_ISDIR(st.st_mode):
            raise ValueError("path phải là file, không phải thư mục")
        if stat.S_ISFIFO(st.st_mode):
            raise ValueError("path phải là regular file, không phải FIFO")
        raise ValueError("path phải là regular file")

    if resolved.suffix.lower() not in (media.AUDIO_EXTS | media.VIDEO_EXTS):
        raise ValueError(f"Định dạng {resolved.suffix} chưa hỗ trợ")

    return resolved


def run_self_test_native() -> int:
    """Import native packages + chạy ffmpeg/ffprobe -version. Trả exit code."""
    from . import media

    lines: list[str] = []
    ok = True
    for name in _NATIVE_PACKAGES:
        try:
            mod = importlib.import_module(name)
            ver = getattr(mod, "__version__", "?")
            extra = ""
            if name == "onnxruntime":
                try:
                    providers = mod.get_available_providers()  # type: ignore[attr-defined]
                    extra = f" providers={providers}"
                except Exception as e:
                    extra = f" providers_error={e}"
            lines.append(f"OK import {name} version={ver}{extra}")
        except Exception as e:
            ok = False
            lines.append(f"FAIL import {name}: {e}")

    for label, getter in (("ffmpeg", media.ffmpeg_path), ("ffprobe", media.ffprobe_path)):
        try:
            exe = getter()
            proc = subprocess.run(
                [exe, "-version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                ok = False
                lines.append(f"FAIL {label} exit={proc.returncode}")
            else:
                first = (proc.stdout or proc.stderr or "").splitlines()[:1]
                lines.append(f"OK {label} path={exe} {first[0] if first else ''}".rstrip())
        except Exception as e:
            ok = False
            lines.append(f"FAIL {label}: {e}")

    print("\n".join(lines), flush=True)
    print("SELF_TEST_NATIVE " + ("PASS" if ok else "FAIL"), flush=True)
    return 0 if ok else 1


def run_uvicorn(
    app,
    sock: socket.socket,
    port: int,
    *,
    open_browser: bool = False,
) -> None:
    """Chạy Uvicorn trên socket đã bind; in READY sau khi started."""
    import threading
    import webbrowser

    import uvicorn

    # Gắn port thực tế cho /healthz
    app.state.actual_port = port
    app.state.uvicorn_server = None

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        workers=1,
        reload=False,
        proxy_headers=False,
        access_log=True,
    )
    server = uvicorn.Server(config)
    app.state.uvicorn_server = server

    _ready_printed = {"done": False}

    original_startup = server.startup

    async def startup_with_ready(sockets=None):
        await original_startup(sockets=sockets)
        if server.started and not _ready_printed["done"]:
            print(format_ready_line(port), flush=True)
            _ready_printed["done"] = True

    server.startup = startup_with_ready  # type: ignore[method-assign]

    if open_browser:
        threading.Timer(
            1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")
        ).start()
        print(f"\n  ViTranscript đang chạy tại http://127.0.0.1:{port}  (Ctrl+C để thoát)\n")

    try:
        server.run(sockets=[sock])
    finally:
        try:
            sock.close()
        except OSError:
            pass


def main_from_args(app, argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    maybe_register_test_model()

    if args.self_test_native:
        raise SystemExit(run_self_test_native())

    sock, port = bind_server_socket(args.port)
    open_browser = not args.no_browser
    # Desktop env flag (informational)
    if os.environ.get("VITRANSCRIPT_DESKTOP") == "1":
        open_browser = False
    run_uvicorn(app, sock, port, open_browser=open_browser)
