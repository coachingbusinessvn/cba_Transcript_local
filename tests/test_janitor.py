"""Tests cho app/janitor.py — GC thư mục jobs/ khi server khởi động."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from app.janitor import cleanup_jobs_dir

_DAY = 86_400


def _make_job(
    jobs_dir: Path,
    name: str,
    status: str = "done",
    age_days: float = 0.0,
    payload_bytes: int = 0,
) -> Path:
    """Tạo job dir giả: status.json (+ payload) với mtime lùi `age_days` ngày."""
    d = jobs_dir / name
    d.mkdir(parents=True)
    status_path = d / "status.json"
    status_path.write_text(json.dumps({"status": status}), encoding="utf-8")
    if payload_bytes:
        (d / "audio16k.wav").write_bytes(b"x" * payload_bytes)
    ts = time.time() - age_days * _DAY
    os.utime(status_path, (ts, ts))
    return d


def _jobs_root(tmp_path: Path) -> Path:
    d = tmp_path / "jobs"
    d.mkdir()
    return d


def test_missing_jobs_dir_returns_zero_stats(tmp_path):
    stats = cleanup_jobs_dir(tmp_path / "khong-ton-tai")
    assert stats == {"removed": 0, "kept": 0, "freed_bytes": 0}


def test_removes_expired_job_and_keeps_fresh(tmp_path):
    jobs = _jobs_root(tmp_path)
    old = _make_job(jobs, "oldjob", age_days=40)
    new = _make_job(jobs, "newjob", age_days=1)

    stats = cleanup_jobs_dir(jobs, max_age_days=30)

    assert not old.exists()
    assert new.exists()
    assert stats["removed"] == 1
    assert stats["kept"] == 1
    assert stats["freed_bytes"] > 0


def test_stale_running_job_removed_by_age_rule(tmp_path):
    """Job "running" nhưng status.json cũ hơn max_age_days = process viết nó đã
    chết từ lâu (GC chạy lúc khởi động, process này chưa thể có job chạy) →
    luật tuổi được phép xóa."""
    jobs = _jobs_root(tmp_path)
    running = _make_job(jobs, "runningjob", status="running", age_days=90)

    stats = cleanup_jobs_dir(jobs, max_age_days=30)

    assert not running.exists()
    assert stats["removed"] == 1
    assert stats["kept"] == 0


def test_fresh_running_job_kept(tmp_path):
    """Job "running" còn mới: có thể là instance khác đang chạy hoặc server vừa
    crash — giữ lại để _get_job khôi phục partial.jsonl."""
    jobs = _jobs_root(tmp_path)
    running = _make_job(jobs, "runningjob", status="running", age_days=0)

    stats = cleanup_jobs_dir(jobs, max_age_days=30)

    assert running.exists()
    assert stats["removed"] == 0
    assert stats["kept"] == 1


def test_running_job_never_removed_by_size_rule(tmp_path):
    """Luật dung lượng miễn nhiễm hoàn toàn với job running: vượt cap thế nào
    cũng không xóa job đang chạy (còn mới) để lấy lại chỗ."""
    jobs = _jobs_root(tmp_path)
    running = _make_job(
        jobs, "runningjob", status="running", age_days=0, payload_bytes=200
    )
    old_done = _make_job(jobs, "donejob", status="done", age_days=0, payload_bytes=200)

    stats = cleanup_jobs_dir(jobs, max_age_days=30, max_total_bytes=1, keep_newest=0)

    assert running.exists()  # running: không bao giờ bị xóa vì dung lượng
    assert not old_done.exists()  # done: bị xóa để cố cứu dung lượng
    assert stats["removed"] == 1
    assert stats["kept"] == 1


def test_pathological_status_json_skips_entry(monkeypatch, tmp_path):
    """status.json làm json.loads ném lỗi không lường (vd RecursionError khi
    lồng quá sâu) → chỉ skip entry đó, không làm hỏng cả pass GC."""
    from app import janitor

    jobs = _jobs_root(tmp_path)
    bad = _make_job(jobs, "badjob", age_days=40)

    def boom(_s, **_kw):
        raise RecursionError("json lồng quá sâu")

    monkeypatch.setattr(janitor.json, "loads", boom)

    stats = janitor.cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    assert bad.exists()
    assert stats["removed"] == 0


def test_size_overflow_removes_oldest_first(tmp_path):
    jobs = _jobs_root(tmp_path)
    dirs = [
        _make_job(jobs, f"j{i}", age_days=float(5 - i), payload_bytes=100)
        for i in range(5)
    ]  # j0 cũ nhất → j4 mới nhất

    # keep_newest=0: chỉ thứ tự xóa (cũ nhất trước) quyết định job nào sống.
    # Mỗi job ~120 byte (status.json + payload) → tổng ~600; cap 350 buộc
    # phải xóa đúng 3 job cũ nhất, 2 job mới nhất sống sót.
    stats = cleanup_jobs_dir(jobs, max_age_days=30, max_total_bytes=350, keep_newest=0)

    assert not dirs[0].exists()
    assert not dirs[1].exists()
    assert not dirs[2].exists()
    assert dirs[3].exists()
    assert dirs[4].exists()
    assert stats["removed"] == 3
    assert stats["kept"] == 2


def test_size_overflow_respects_keep_newest(tmp_path):
    jobs = _jobs_root(tmp_path)
    dirs = [
        _make_job(jobs, f"j{i}", age_days=float(5 - i), payload_bytes=100)
        for i in range(5)
    ]

    # Cap nhỏ → chỉ được xóa job ngoài 3 job mới nhất (j2, j3, j4 được giữ
    # dù tổng vẫn vượt cap).
    stats = cleanup_jobs_dir(jobs, max_age_days=30, max_total_bytes=1, keep_newest=3)

    assert not dirs[0].exists()
    assert not dirs[1].exists()
    assert dirs[2].exists()
    assert dirs[3].exists()
    assert dirs[4].exists()
    assert stats["removed"] == 2
    assert stats["kept"] == 3


def test_corrupt_or_non_dict_status_is_skipped(tmp_path):
    jobs = _jobs_root(tmp_path)
    bad = jobs / "badjob"
    bad.mkdir()
    bad_status = bad / "status.json"
    bad_status.write_text("không phải json {{{", encoding="utf-8")
    arr = jobs / "arrjob"
    arr.mkdir()
    arr_status = arr / "status.json"
    arr_status.write_text("[1, 2, 3]", encoding="utf-8")
    ts = time.time() - 40 * _DAY
    os.utime(bad_status, (ts, ts))
    os.utime(arr_status, (ts, ts))

    stats = cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    assert bad.exists()
    assert arr.exists()
    assert stats["removed"] == 0


def test_stray_dir_without_status_is_kept(tmp_path):
    jobs = _jobs_root(tmp_path)
    stray = jobs / "not-a-job"
    stray.mkdir()
    (stray / "junk.bin").write_bytes(b"z" * 50)
    old = _make_job(jobs, "realjob", age_days=40)

    stats = cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    assert stray.exists()
    assert not old.exists()
    assert stats["removed"] == 1
    assert stats["kept"] == 0  # stray không tính là job


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="monkeypatch os.stat không chặn được Path.lstat() trên Python 3.10 "
    "(lstat bind os.lstat trực tiếp qua _accessor, không tra os.stat lúc gọi) "
    "nên tag giả không được gắn — test chỉ có ý nghĩa trên 3.11+; uv pin 3.12",
)
def test_reparse_point_job_dir_skipped(monkeypatch, tmp_path):
    """Junction/reparse point trên Windows KHÔNG phải symlink nên is_symlink()
    không bắt được: entry.is_dir() theo junction trả True và rmtree (Python
    <3.12) đi theo junction xóa cả target bên ngoài jobs/. GC phải bỏ qua
    mọi entry có st_reparse_tag — giả lập bằng cách gắn tag vào lstat
    (Path.lstat trên 3.11/3.12 = os.stat(follow_symlinks=False))."""
    from app import janitor

    jobs = _jobs_root(tmp_path)
    jdir = _make_job(jobs, "junctionjob", age_days=40)
    real_stat = os.stat

    class _FakeStat:
        """stat_result giả: delegate mọi field thật, chỉ thêm st_reparse_tag
        (field này chỉ tồn tại trong stat_result trên Windows)."""

        def __init__(self, real):
            self._real = real
            self.st_reparse_tag = 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_stat(path, *a, **k):
        real = real_stat(path, *a, **k)
        # lstat (không follow) trên junction mới trả reparse tag; stat thường
        # (is_dir) vẫn đi xuyên junction như Windows thật.
        if Path(path) == jdir and k.get("follow_symlinks") is False:
            return _FakeStat(real)
        return real

    monkeypatch.setattr(janitor.os, "stat", fake_stat)

    stats = janitor.cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    assert jdir.exists()          # không xóa junction, tuyệt đối không đi theo
    assert stats["removed"] == 0


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="cùng lý do test_reparse_point_job_dir_skipped: Path.lstat() trên "
    "3.10 không đi qua os.stat nên monkeypatch không gắn được reparse tag",
)
def test_nested_reparse_point_keeps_job_dir(monkeypatch, tmp_path):
    """Job dir hợp lệ chứa junction/reparse point LỒNG bên trong vẫn nguy
    hiểm: check top-level trong _list_valid_jobs không nhìn thấy nó, và
    rmtree (Python <3.12) đi theo junction → xóa cả target ngoài jobs/.
    GC phải giữ nguyên job dir (đếm là kept), conservative: cấu trúc lạ →
    không xóa. Test này đi qua luật TUỔI (status.json cũ 40 ngày)."""
    from app import janitor

    jobs = _jobs_root(tmp_path)
    jdir = _make_job(jobs, "nestedjob", age_days=40)
    nested = jdir / "nested"
    nested.mkdir()
    real_stat = os.stat

    class _FakeStat:
        def __init__(self, real):
            self._real = real
            self.st_reparse_tag = 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_stat(path, *a, **k):
        real = real_stat(path, *a, **k)
        if Path(path) == nested and k.get("follow_symlinks") is False:
            return _FakeStat(real)
        return real

    monkeypatch.setattr(janitor.os, "stat", fake_stat)

    stats = janitor.cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    assert jdir.exists()
    assert nested.exists()
    assert stats["removed"] == 0
    assert stats["kept"] == 1


@pytest.mark.skipif(os.name == "nt", reason="symlink cần quyền admin trên Windows")
def test_nested_symlink_keeps_job_dir(tmp_path):
    """Symlink lồng trong job dir trỏ ra ngoài jobs/: cùng lý do conservative
    — thấy symlink/reparse ở bất kỳ độ sâu nào thì giữ nguyên job dir.
    Test này đi qua luật DUNG LƯỢNG (job mới, cap nhỏ) — bù luật tuổi đã
    cover ở test reparse phía trên."""
    jobs = _jobs_root(tmp_path)
    jdir = _make_job(jobs, "nestedlink", status="done", age_days=0)
    outside = tmp_path / "outside"
    outside.mkdir()
    (jdir / "link").symlink_to(outside, target_is_directory=True)

    stats = cleanup_jobs_dir(jobs, max_age_days=30, max_total_bytes=1, keep_newest=0)

    assert jdir.exists()
    assert outside.exists()
    assert stats["removed"] == 0
    assert stats["kept"] == 1


@pytest.mark.skipif(os.name == "nt", reason="symlink cần quyền admin trên Windows")
def test_symlinked_job_dir_not_removed(tmp_path):
    jobs = _jobs_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    status_path = outside / "status.json"
    status_path.write_text(json.dumps({"status": "done"}), encoding="utf-8")
    ts = time.time() - 40 * _DAY
    os.utime(status_path, (ts, ts))
    link = jobs / "linkjob"
    link.symlink_to(outside, target_is_directory=True)

    stats = cleanup_jobs_dir(jobs, max_age_days=30, keep_newest=0)

    # Không xóa symlink (và tuyệt đối không xóa target bên ngoài jobs/).
    assert link.is_symlink()
    assert outside.exists()
    assert status_path.exists()
    assert stats["removed"] == 0
