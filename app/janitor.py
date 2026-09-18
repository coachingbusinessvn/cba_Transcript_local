"""Dọn thư mục jobs/ — GC chạy một lần khi server khởi động.

Mỗi job giữ input gốc + wav 16k (+ audio tách từ video) nên jobs/ phình theo
thời gian. Chính sách: xóa job quá `max_age_days` ngày (theo mtime status.json);
nếu tổng jobs/ vẫn vượt `max_total_bytes` thì xóa tiếp job cũ nhất trước, nhưng
không bao giờ đụng `keep_newest` job mới nhất — luôn giữ lại vài kết quả gần đây.

An toàn: chỉ xóa thư mục con có status.json là dict JSON hợp lệ, không xóa job
`status == "running"`, không follow symlink ra ngoài jobs/, entry không đọc
được thì bỏ qua. GC chỉ chạy lúc khởi động (server chưa nhận job) nên không có
race với job đang ghi.
"""
import json
import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger("vitranscript")

_SECONDS_PER_DAY = 86_400


def _tree_size(path: Path) -> int:
    """Tổng byte các file trong cây thư mục — không đi theo symlink (followlinks=False)."""
    total = 0
    try:
        for root, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass  # file biến mất giữa chừng / không đọc được — bỏ qua
    except OSError:
        pass
    return total


def _read_status(path: Path) -> dict | None:
    """status.json hợp lệ = JSON dict; hỏng/không phải dict/không đọc được → None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _list_valid_jobs(jobs_dir: Path) -> list[tuple[Path, float, bool]]:
    """Các job dir hợp lệ: (path, mtime status.json, đang chạy?). Mới nhất trước."""
    jobs = []
    try:
        entries = list(jobs_dir.iterdir())
    except OSError:
        return jobs
    for entry in entries:
        try:
            # Không follow symlink: rmtree trên symlink tới thư mục sẽ xóa cả
            # target ngoài jobs/ (hoặc ném lỗi) — bỏ qua hoàn toàn.
            if entry.is_symlink() or not entry.is_dir():
                continue
            status_path = entry / "status.json"
            status = _read_status(status_path)
            if status is None:
                continue
            mtime = status_path.stat().st_mtime
        except OSError:
            continue
        jobs.append((entry, mtime, status.get("status") == "running"))
    jobs.sort(key=lambda j: j[1], reverse=True)
    return jobs


def cleanup_jobs_dir(
    jobs_dir: Path,
    max_age_days: int = 30,
    max_total_bytes: int = 20 << 30,
    keep_newest: int = 10,
) -> dict:
    """Xóa job dir khi thỏa ÍT NHẤT MỘT điều kiện:

    - status.json cũ hơn `max_age_days` ngày (mtime), HOẶC
    - tổng jobs/ vượt `max_total_bytes` → xóa cũ nhất trước, nhưng không đụng
      `keep_newest` job mới nhất (xếp theo mtime status.json).

    Trả về {"removed", "kept", "freed_bytes"}.
    """
    removed = 0
    freed = 0

    def _remove(path: Path) -> int:
        """Xóa một job dir; trả về số byte giải phóng (0 nếu rmtree lỗi)."""
        nonlocal removed, freed
        size = _tree_size(path)  # đo trước khi xóa — sau rmtree không còn gì để đo
        try:
            shutil.rmtree(path)
        except OSError as e:
            log.warning("GC jobs/: không xóa được %s: %s", path, e)
            return 0
        removed += 1
        freed += size
        return size

    jobs = _list_valid_jobs(jobs_dir)
    total = _tree_size(jobs_dir)  # gồm cả stray file/dir — chúng cũng chiếm đĩa
    cutoff = time.time() - max_age_days * _SECONDS_PER_DAY

    # Luật tuổi trước: job quá hạn bị xóa vô điều kiện (keep_newest chỉ chặn
    # luật dung lượng). Job còn hạn nhưng nằm ngoài keep_newest mới nhất là ứng
    # viên cho luật dung lượng — gom lại, xử lý sau khi biết phần đĩa đã được
    # giải phóng bởi luật tuổi.
    size_candidates: list[Path] = []
    for rank, (path, mtime, running) in enumerate(jobs):
        if running:
            continue  # không bao giờ xóa job đang chạy
        if mtime < cutoff:
            total -= _remove(path)
        elif rank >= keep_newest:
            size_candidates.append(path)

    # Luật dung lượng: vẫn vượt cap → xóa cũ nhất trước (size_candidates đang
    # xếp mới → cũ nên duyệt ngược) tới khi đủ chỗ hoặc hết job được phép xóa.
    for path in reversed(size_candidates):
        if total <= max_total_bytes:
            break
        total -= _remove(path)

    return {"removed": removed, "kept": len(jobs) - removed, "freed_bytes": freed}
