"""Integration test qua uvicorn thật trên socket loopback.

TestClient đi qua cùng ASGI stack nhưng không chạy qua TCP + uvicorn header
pipeline — file này boot server thật để chứng minh middleware `_security_guard`
hoạt động end-to-end. Không gọi `main()` (không mở browser, không chạy janitor).
"""
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app import server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_server():
    """Boot uvicorn.Server thật trong daemon thread; teardown shutdown sạch."""
    port = _free_port()
    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    jobs_before = dict(server.JOBS)
    thread.start()
    try:
        # Đợi port accept — tối đa ~5s, không chờ vô hạn.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not thread.is_alive():
                raise RuntimeError("uvicorn thread chết trong lúc startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.02)
        else:
            raise RuntimeError(f"uvicorn không accept port {port} trong 5s")
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            yield client
    finally:
        srv.should_exit = True
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "uvicorn thread không thoát sau 5s"
        assert server.JOBS == jobs_before, "test không được tạo job thật"


def test_get_index_loopback_ok_with_security_headers(live_server):
    r = live_server.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Security headers do middleware gắn — phải có trên response thật qua socket.
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_non_loopback_host_rejected(live_server):
    """DNS rebinding: domain attacker resolve về 127.0.0.1 nhưng trình duyệt
    giữ nguyên Host của domain → guard trả 403 trước khi tới route."""
    r = live_server.get("/", headers={"Host": "evil.example"})
    assert r.status_code == 403
    # Kèm port trong Host cũng không lách được (guard tách port trước khi check).
    r = live_server.get("/", headers={"Host": "evil.example:1234"})
    assert r.status_code == 403


def test_post_cross_site_origin_rejected(live_server):
    """CSRF: POST mang Origin của site khác bị chặn — không tới route /api/jobs."""
    r = live_server.post("/api/jobs", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_post_cross_site_fetch_site_rejected(live_server):
    """CSRF: trình duyệt gắn Sec-Fetch-Site: cross-site trên form/fetch chéo → 403."""
    r = live_server.post("/api/jobs", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_same_origin_post_passes_guard(live_server):
    """Đối chứng: POST same-origin qua được guard → tới route thật và lỗi
    validate 422 (thiếu file/model) — chứng tỏ guard không chặn quá tay."""
    r = live_server.post("/api/jobs", headers={"Origin": "http://127.0.0.1:8756"})
    assert r.status_code == 422


def test_api_response_has_no_store_header(live_server):
    """GET /api/* phải mang Cache-Control: no-store. job_id sai format bị 404
    bởi _JOB_ID_RE trước khi chạm jobs_dir — không đụng đĩa."""
    r = live_server.get("/api/jobs/not-a-job-id")
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
