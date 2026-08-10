"""TDD: hợp đồng desktop sidecar — port/READY/healthz/local job/shutdown/self-test."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import config, media, server
from app import server_runtime as runtime

# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def test_cli_port_default_is_dynamic():
    args = runtime.parse_args([])
    assert args.port == 0
    assert args.no_browser is False
    assert args.self_test_native is False


def test_cli_port_zero_is_dynamic():
    args = runtime.parse_args(["--port", "0"])
    assert args.port == 0


def test_cli_port_fixed_valid():
    args = runtime.parse_args(["--port", "8765", "--no-browser"])
    assert args.port == 8765
    assert args.no_browser is True


@pytest.mark.parametrize("bad", ["-1", "65536", "abc", "87.5"])
def test_cli_port_invalid_raises(bad):
    with pytest.raises(SystemExit):
        runtime.parse_args(["--port", bad])


# ---------------------------------------------------------------------------
# Socket bind (giữ socket, không TOCTOU)
# ---------------------------------------------------------------------------


def test_bind_dynamic_skips_occupied_port():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", runtime.PORT_RANGE_START))
    holder.listen(1)
    try:
        sock, port = runtime.bind_server_socket(0)
        try:
            assert port == runtime.PORT_RANGE_START + 1
            assert sock.getsockname()[1] == port
            # Socket vẫn bind — port không trống nếu thử bind lần 2
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with pytest.raises(OSError):
                probe.bind(("127.0.0.1", port))
            probe.close()
        finally:
            sock.close()
    finally:
        holder.close()


def test_bind_fixed_port_occupied_fails():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    fixed = holder.getsockname()[1]
    try:
        with pytest.raises(RuntimeError, match="(?i)bind|port|chiếm"):
            runtime.bind_server_socket(fixed)
    finally:
        holder.close()


def test_bind_fixed_port_success():
    # Chọn port tự do rồi đóng, bind lại fixed — có race nhỏ nhưng chấp nhận trong unit
    tmp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tmp.bind(("127.0.0.1", 0))
    port = tmp.getsockname()[1]
    tmp.close()
    sock, got = runtime.bind_server_socket(port)
    try:
        assert got == port
        assert sock.getsockname()[1] == port
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Pure auth helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host,ok",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("8.8.8.8", False),
        ("192.168.1.1", False),
        ("testclient", False),
        ("", False),
    ],
)
def test_is_loopback_host(host, ok):
    assert runtime.is_loopback_host(host) is ok


def test_token_compare_constant_time_and_missing():
    assert runtime.tokens_match("abc", "abc") is True
    assert runtime.tokens_match("abc", "abd") is False
    assert runtime.tokens_match(None, "abc") is False
    assert runtime.tokens_match("abc", None) is False
    assert runtime.tokens_match("", "abc") is False
    # Unequal length: still False, only via compare_digest (no early len branch leak).
    assert runtime.tokens_match("short", "much-longer-token-value") is False
    assert runtime.tokens_match("much-longer-token-value", "short") is False
    # Strip normalization
    assert runtime.tokens_match("  abc  ", "abc") is True


# ---------------------------------------------------------------------------
# Path validation for local jobs
# ---------------------------------------------------------------------------


def test_validate_local_path_happy(tmp_path):
    f = tmp_path / "hop.wav"
    f.write_bytes(b"RIFF")
    got = runtime.validate_local_media_path(str(f))
    assert got == f.resolve(strict=True)
    assert got.is_file()


def test_validate_local_path_rejects_relative():
    with pytest.raises(ValueError, match="(?i)absolute|tuyệt đối|relative"):
        runtime.validate_local_media_path("rel/file.wav")


def test_validate_local_path_rejects_nul():
    with pytest.raises(ValueError, match="(?i)NUL|null|\\x00"):
        runtime.validate_local_media_path("/tmp/a\x00.wav")


def test_validate_local_path_rejects_dotdot(tmp_path):
    f = tmp_path / "ok.wav"
    f.write_bytes(b"x")
    # absolute nhưng chứa component ..
    bad = str(tmp_path / "sub" / ".." / "ok.wav")
    with pytest.raises(ValueError, match=r"\.\."):
        runtime.validate_local_media_path(bad)


def test_validate_local_path_rejects_missing(tmp_path):
    with pytest.raises(ValueError, match="(?i)tồn tại|exist|không tìm"):
        runtime.validate_local_media_path(str(tmp_path / "nope.wav"))


def test_validate_local_path_rejects_directory(tmp_path):
    with pytest.raises(ValueError, match="(?i)thư mục|directory|file"):
        runtime.validate_local_media_path(str(tmp_path))


def test_validate_local_path_rejects_suffix(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="(?i)định dạng|suffix|hỗ trợ"):
        runtime.validate_local_media_path(str(f))


def test_validate_local_path_rejects_symlink_file(tmp_path):
    real = tmp_path / "real.wav"
    real.write_bytes(b"x")
    link = tmp_path / "link.wav"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="(?i)symlink|liên kết"):
        runtime.validate_local_media_path(str(link))


def test_validate_local_path_rejects_symlink_parent(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    f = real_dir / "a.wav"
    f.write_bytes(b"x")
    link_dir = tmp_path / "linkdir"
    link_dir.symlink_to(real_dir)
    with pytest.raises(ValueError, match="(?i)symlink|liên kết"):
        runtime.validate_local_media_path(str(link_dir / "a.wav"))


@pytest.mark.skipif(sys.platform == "win32", reason="FIFO chỉ POSIX")
def test_validate_local_path_rejects_fifo(tmp_path):
    fifo = tmp_path / "pipe.wav"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="(?i)FIFO|regular|file"):
        runtime.validate_local_media_path(str(fifo))


def test_validate_local_path_windows_reparse_helper(monkeypatch, tmp_path):
    f = tmp_path / "j.wav"
    f.write_bytes(b"x")
    # Giả lập Windows reparse: helper báo component có reparse point
    monkeypatch.setattr(runtime, "_is_windows_reparse", lambda p: p.name == "j.wav")
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(ValueError, match="(?i)reparse|junction"):
        runtime.validate_local_media_path(str(f))


def test_validate_local_path_windows_reparse_api_failure_fail_closed(monkeypatch, tmp_path):
    """API GetFileAttributes lỗi → reject path (fail-closed), không accept."""
    f = tmp_path / "x.wav"
    f.write_bytes(b"x")

    def boom(_p):
        raise OSError(5, "GetFileAttributesW failed")

    monkeypatch.setattr(runtime, "_is_windows_reparse", boom)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(ValueError, match="(?i)thuộc tính|reparse|attribute"):
        runtime.validate_local_media_path(str(f))


# ---------------------------------------------------------------------------
# Healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_ok_and_port(monkeypatch):
    monkeypatch.setattr(server.app.state, "actual_port", 8765, raising=False)
    c = TestClient(server.app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "port": 8765}


# ---------------------------------------------------------------------------
# Shutdown endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setenv("VITRANSCRIPT_INSTANCE_TOKEN", "secret-token-xyz")
    yield "secret-token-xyz"
    # cleanup handled by monkeypatch


def test_shutdown_requires_token_configured(monkeypatch):
    monkeypatch.delenv("VITRANSCRIPT_INSTANCE_TOKEN", raising=False)
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    c = TestClient(server.app)
    r = c.post("/api/shutdown", headers={"X-ViTranscript-Token": "x"})
    assert r.status_code == 404


def test_shutdown_rejects_non_loopback(token_env, monkeypatch):
    monkeypatch.setattr(server, "_client_host", lambda r: "8.8.8.8")
    c = TestClient(server.app)
    r = c.post("/api/shutdown", headers={"X-ViTranscript-Token": token_env})
    assert r.status_code == 403


def test_shutdown_rejects_missing_token(token_env, monkeypatch):
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    c = TestClient(server.app)
    r = c.post("/api/shutdown")
    assert r.status_code == 403


def test_shutdown_rejects_wrong_token(token_env, monkeypatch):
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    c = TestClient(server.app)
    r = c.post("/api/shutdown", headers={"X-ViTranscript-Token": "wrong"})
    assert r.status_code == 403


def test_shutdown_ok_calls_callback_once(token_env, monkeypatch):
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    calls: list[int] = []
    monkeypatch.setattr(server, "_request_shutdown", lambda: calls.append(1))
    c = TestClient(server.app)
    r = c.post("/api/shutdown", headers={"X-ViTranscript-Token": token_env})
    assert r.status_code == 202
    # BackgroundTask may run after response in TestClient
    assert calls == [1] or len(calls) == 1


# ---------------------------------------------------------------------------
# Local job endpoint
# ---------------------------------------------------------------------------


def _fake_pipeline_result():
    return {
        "sentences": [{"start": 0.0, "end": 1.0, "text": "xin chào", "speaker": None}],
        "duration": 1.0,
        "num_speakers": 0,
        "extracted_audio": None,
        "model": "phowhisper-small",
        "punctuation": {"requested": False, "applied": False, "warning": None},
    }


@pytest.fixture
def local_job_env(monkeypatch, tmp_path, token_env):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(media, "duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    server.JOBS.clear()
    # Không chạy pipeline thật — stub thread target
    started: list[tuple] = []

    def capture_thread(target, args, daemon=True):
        t = MagicMock()
        started.append((target, args, daemon))

        def start():
            # Chạy sync để job hoàn tất ngay (hoặc chỉ reserve)
            pass

        t.start = start
        return t

    monkeypatch.setattr(server.threading, "Thread", capture_thread)
    yield tmp_path, token_env, started
    server.JOBS.clear()


def test_local_job_happy_ipv4(local_job_env, monkeypatch):
    tmp_path, token, started = local_job_env
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFF")
    c = TestClient(server.app)
    body = {
        "path": str(f),
        "model": "phowhisper-small",
        "language": "vi",
        "diarize": False,
        "punctuate": False,
        "num_speakers": 0,
        "glossary": "NVIDIA",
    }
    r = c.post(
        "/api/jobs/local",
        json=body,
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "job_id" in data
    job_id = data["job_id"]
    assert len(started) == 1
    target, args, daemon = started[0]
    assert daemon is True
    # args: (job_id, input_path, opts, output_dir)
    assert args[0] == job_id
    assert Path(args[1]) == f.resolve(strict=True)
    assert args[2]["model"] == "phowhisper-small"
    assert args[2]["glossary"] == "NVIDIA"
    assert Path(args[3]) == config.jobs_dir() / job_id


def test_local_job_happy_ipv6(local_job_env, monkeypatch, token_env):
    tmp_path, token, started = local_job_env
    monkeypatch.setattr(server, "_client_host", lambda r: "::1")
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3")
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "phowhisper-small"},
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 200


def test_local_job_rejects_non_loopback(local_job_env, monkeypatch):
    tmp_path, token, _ = local_job_env
    monkeypatch.setattr(server, "_client_host", lambda r: "10.0.0.1")
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "phowhisper-small"},
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 403


def test_local_job_rejects_bad_token(local_job_env):
    tmp_path, token, _ = local_job_env
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "phowhisper-small"},
        headers={"X-ViTranscript-Token": "nope"},
    )
    assert r.status_code == 403


def test_local_job_rejects_relative_path(local_job_env):
    _, token, _ = local_job_env
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": "rel.wav", "model": "phowhisper-small"},
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 400


def test_local_job_bad_model_400(local_job_env):
    tmp_path, token, _ = local_job_env
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "not-a-model"},
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 400


def test_local_job_active_returns_409(local_job_env):
    tmp_path, token, _ = local_job_env
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    server.JOBS["busy"] = {"status": "running"}
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "phowhisper-small"},
        headers={"X-ViTranscript-Token": token},
    )
    assert r.status_code == 409


def test_local_job_releases_on_thread_start_fail(monkeypatch, tmp_path, token_env):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(media, "duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(server, "_client_host", lambda r: "127.0.0.1")
    server.JOBS.clear()

    class Boom:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(server.threading, "Thread", Boom)
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    c = TestClient(server.app)
    with pytest.raises(RuntimeError, match="can't start"):
        c.post(
            "/api/jobs/local",
            json={"path": str(f), "model": "phowhisper-small"},
            headers={"X-ViTranscript-Token": token_env},
        )
    assert server.JOBS == {}


def test_local_job_forged_xff_does_not_bypass(local_job_env, monkeypatch):
    """X-Forwarded-For không thay peer; peer non-loopback vẫn 403."""
    tmp_path, token, _ = local_job_env
    monkeypatch.setattr(server, "_client_host", lambda r: "203.0.113.1")
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    c = TestClient(server.app)
    r = c.post(
        "/api/jobs/local",
        json={"path": str(f), "model": "phowhisper-small"},
        headers={
            "X-ViTranscript-Token": token,
            "X-Forwarded-For": "127.0.0.1",
        },
    )
    assert r.status_code == 403


def test_no_cors_headers_on_options(monkeypatch):
    c = TestClient(server.app)
    r = c.options(
        "/api/jobs/local",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Không có CORS allow
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers.keys()}


def test_run_job_uses_explicit_output_dir(monkeypatch, tmp_path):
    from app import pipeline

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    captured = {}

    def fake_run(input_path, work_dir, model_key, **kwargs):
        captured["input"] = Path(input_path)
        captured["work"] = Path(work_dir)
        return _fake_pipeline_result()

    monkeypatch.setattr(pipeline, "run", fake_run)
    server.JOBS.clear()
    server.JOBS["jout"] = {
        "status": "running",
        "filename": "src.wav",
        "model": "phowhisper-small",
    }
    src = tmp_path / "elsewhere" / "src.wav"
    src.parent.mkdir()
    src.write_bytes(b"x")
    out = tmp_path / "jobs" / "jout"
    out.mkdir(parents=True)
    server._run_job(
        "jout",
        src,
        {
            "model": "phowhisper-small",
            "language": "vi",
            "diarize": False,
            "punctuate": False,
            "num_speakers": 0,
            "glossary": "",
        },
        output_dir=out,
    )
    assert captured["input"] == src
    assert captured["work"] == out


# ---------------------------------------------------------------------------
# Test model gate
# ---------------------------------------------------------------------------


def test_test_model_not_registered_by_default(monkeypatch):
    monkeypatch.delenv("VITRANSCRIPT_ENABLE_TEST_MODEL", raising=False)
    # clear any prior registration
    config.MODEL_REGISTRY.pop("tiny-test", None)
    runtime.maybe_register_test_model()
    assert "tiny-test" not in config.MODEL_REGISTRY


def test_test_model_registered_when_env_set(monkeypatch):
    monkeypatch.setenv("VITRANSCRIPT_ENABLE_TEST_MODEL", "1")
    config.MODEL_REGISTRY.pop("tiny-test", None)
    runtime.maybe_register_test_model()
    assert "tiny-test" in config.MODEL_REGISTRY
    assert config.MODEL_REGISTRY["tiny-test"]["source"] == "tiny"
    # cleanup
    config.MODEL_REGISTRY.pop("tiny-test", None)
    monkeypatch.delenv("VITRANSCRIPT_ENABLE_TEST_MODEL", raising=False)


# ---------------------------------------------------------------------------
# Self-test native (unit, monkeypatch — không tải model)
# ---------------------------------------------------------------------------


def test_self_test_native_success(monkeypatch, capsys):
    import types

    fake_pkgs = {
        "ctranslate2": types.SimpleNamespace(__version__="4.0.0"),
        "onnxruntime": types.SimpleNamespace.__new__(types.SimpleNamespace),
        "sherpa_onnx": types.SimpleNamespace(__version__="1.0"),
        "tokenizers": types.SimpleNamespace(__version__="0.20"),
        "faster_whisper": types.SimpleNamespace(__version__="1.1"),
        "av": types.SimpleNamespace(__version__="12.0"),
        "static_ffmpeg": types.SimpleNamespace(__version__="2.7"),
    }
    fake_pkgs["onnxruntime"].__version__ = "1.20"
    fake_pkgs["onnxruntime"].get_available_providers = lambda: ["CPUExecutionProvider"]

    def fake_import(name, package=None):
        if name in fake_pkgs:
            return fake_pkgs[name]
        raise ImportError(name)

    monkeypatch.setattr(runtime.importlib, "import_module", fake_import)
    monkeypatch.setattr(media, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(media, "ffprobe_path", lambda: "ffprobe")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{cmd[0]} version 6.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    code = runtime.run_self_test_native()
    assert code == 0
    out = capsys.readouterr().out
    assert "ctranslate2" in out
    assert "ffmpeg" in out


def test_self_test_native_fails_on_missing_import(monkeypatch):
    def boom(name, package=None):
        raise ImportError(name)

    monkeypatch.setattr(runtime.importlib, "import_module", boom)
    code = runtime.run_self_test_native()
    assert code != 0


# ---------------------------------------------------------------------------
# READY line format helper
# ---------------------------------------------------------------------------


def test_ready_line_format():
    line = runtime.format_ready_line(8765)
    assert line == "VITRANSCRIPT_READY http://127.0.0.1:8765"
    assert runtime.READY_LINE_RE.match(line)
    m = runtime.READY_LINE_RE.match(line)
    assert m is not None
    assert m.group(1) == "8765"


# ---------------------------------------------------------------------------
# Subprocess contract: real server --port 0 --no-browser
# ---------------------------------------------------------------------------


@pytest.mark.timeout(60)
def test_subprocess_ready_healthz_shutdown(tmp_path, monkeypatch):
    """Chạy python -m app.server; đọc stdout async tới exit; đúng 1 READY; exit 0."""
    import threading
    import urllib.request

    env = os.environ.copy()
    env["VITRANSCRIPT_INSTANCE_TOKEN"] = "e2e-token-test-0123456789abcdef"
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "app.server", "--port", "0", "--no-browser"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: list[str] = []
    ready_event = threading.Event()
    ready_port_box: list[int] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n\r")
            lines.append(line)
            m = runtime.READY_LINE_RE.match(line)
            if m and not ready_port_box:
                ready_port_box.append(int(m.group(1)))
                ready_event.set()
        # EOF when process closes stdout

    reader_t = threading.Thread(target=_reader, daemon=True)
    reader_t.start()

    try:
        # True deadline: wait for READY without blocking forever on readline in main.
        assert ready_event.wait(timeout=30), (
            f"không thấy READY trong 30s; exit={proc.poll()}; lines={lines!r}"
        )
        ready_port = ready_port_box[0]

        url = f"http://127.0.0.1:{ready_port}/healthz"
        with urllib.request.urlopen(url, timeout=2) as resp:
            body = json.loads(resp.read().decode())
        assert body == {"status": "ok", "port": ready_port}

        req = urllib.request.Request(
            f"http://127.0.0.1:{ready_port}/api/shutdown",
            method="POST",
            headers={"X-ViTranscript-Token": env["VITRANSCRIPT_INSTANCE_TOKEN"]},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 202

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
            pytest.fail("sidecar không thoát sau shutdown")

        reader_t.join(timeout=3)
        # Đếm TẤT CẢ READY sau khi process exit (reader drain hết stdout).
        ready_lines = [ln for ln in lines if runtime.READY_LINE_RE.match(ln)]
        assert len(ready_lines) == 1, f"expected exactly 1 READY, got {ready_lines!r}"
        assert proc.returncode == 0, f"expected exit 0, got {proc.returncode}"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


def test_frozen_ffmpeg_prefers_bundle(monkeypatch, tmp_path):
    bin_dir = tmp_path / "ffmpeg"
    bin_dir.mkdir()
    ff = bin_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fp = bin_dir / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    ff.write_text("#!/bin/sh\n", encoding="utf-8")
    fp.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert Path(media.ffmpeg_path()) == ff
    assert Path(media.ffprobe_path()) == fp


def test_frozen_missing_ffprobe_does_not_use_bundle(monkeypatch, tmp_path):
    """CR-3: thiếu ffprobe bundled → không trả path ảo (bypass guard file dài)."""
    bin_dir = tmp_path / "ffmpeg"
    bin_dir.mkdir()
    ff = bin_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    ff.write_text("#!/bin/sh\n", encoding="utf-8")
    # không tạo ffprobe
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert media._bundled_ffmpeg_dir() is None
    # ffprobe_path không được trả path không tồn tại trong bundle
    fp_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    missing = bin_dir / fp_name
    got = media.ffprobe_path()
    assert Path(got) != missing
    # nếu path nằm dưới MEIPASS thì phải tồn tại (không bypass bằng path ma)
    if str(tmp_path) in got:
        assert Path(got).is_file()


def test_local_job_num_speakers_out_of_range(local_job_env):
    """CR-6: num_speakers ngoài [0,20] → 400 chuỗi tiếng Việt (không 422 list)."""
    tmp_path, token, _started = local_job_env
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFF")
    c = TestClient(server.app)
    for bad in (-1, 21, 100):
        body = {
            "path": str(f),
            "model": "phowhisper-small",
            "language": "vi",
            "diarize": False,
            "punctuate": False,
            "num_speakers": bad,
            "glossary": "",
        }
        r = c.post(
            "/api/jobs/local",
            json=body,
            headers={"X-ViTranscript-Token": token},
        )
        assert r.status_code == 400, (bad, r.status_code, r.text)
        detail = r.json()["detail"]
        assert isinstance(detail, str), detail
        assert "0" in detail and "20" in detail
        assert "[object Object]" not in detail


def test_local_job_num_speakers_boundary_ok(local_job_env):
    """num_speakers 0 và 20 vẫn chấp nhận."""
    tmp_path, token, started = local_job_env
    f = tmp_path / "sample.wav"
    f.write_bytes(b"RIFF")
    c = TestClient(server.app)
    for ok in (0, 20):
        started.clear()
        server.JOBS.clear()  # v1: 1 job — xóa reservation giả từ lần trước
        body = {
            "path": str(f),
            "model": "phowhisper-small",
            "language": "vi",
            "diarize": False,
            "punctuate": False,
            "num_speakers": ok,
            "glossary": "",
        }
        r = c.post(
            "/api/jobs/local",
            json=body,
            headers={"X-ViTranscript-Token": token},
        )
        assert r.status_code == 200, (ok, r.text)
        assert len(started) == 1
        assert started[0][1][2]["num_speakers"] == ok
