# Plan: security follow-up + next-plan execution (2026-09-18)

Tiếp nối commit `a4e915a` (security hardening). Phạm vi: các việc làm được
trên máy này (macOS x86_64); các việc cần máy Windows / dữ liệu người dùng
được nêu rõ là BLOCKED thay vì làm hờ.

## Global Constraints

- Theo sát `CLAUDE.md`/`AGENTS.md`: Python 3.10–3.12, không PyTorch/TF,
  `uv run ruff check .` sạch trước commit, test viết trước khi sửa code.
- `job_id` thật luôn là uuid-hex-12 (`_JOB_ID_RE`) — test fixture phải dùng id hợp lệ.
- Middleware `_security_guard`: Host loopback-only; POST chặn Origin/Sec-Fetch-Site
  cross-site. Mọi TestClient phải dùng `base_url="http://127.0.0.1"`.
- Không phá hành vi hiện có: 1 job/lần (409), checkpoint `partial.jsonl`,
  jobs dir lưu trong `config.jobs_dir()`.
- Cập nhật `CLAUDE.md` + `AGENTS.md` trong cùng commit khi thêm constraint/module/script.

## Task 1 — Jobs-dir GC (janitor)

Vấn đề: `jobs/` không bao giờ được dọn — mỗi job giữ input gốc + wav 16k + audio
tách; file dài nhiều GB/job làm đầy đĩa theo thời gian. Hiện README bảo xóa tay.

Thiết kế (giữ đơn giản, không auto-delete kết quả mới):

- `app/janitor.py` (module mới) export `cleanup_jobs_dir(jobs_dir, max_age_days=30,
  max_total_bytes=20<<30, keep_newest=10) -> dict` trả về thống kê
  `{removed, kept, freed_bytes}`.
- Quy tắc xóa một job dir, thỏa ÍT NHẤT MỘT điều kiện:
  - `status.json` cũ hơn `max_age_days` ngày (mtime), HOẶC
  - tổng dung lượng jobs/ vượt `max_total_bytes` → xóa job cũ nhất trước,
    nhưng không đụng `keep_newest` job mới nhất (theo mtime status.json).
- AN TOÀN: chỉ xóa thư mục con của jobs_dir có status.json hợp lệ (dict JSON);
  không bao giờ xóa job có `status == "running"`; skip entry không đọc được.
  Không follow symlink ra ngoài (dùng `Path.is_symlink()` check trên job dir).
- Gọi `janitor.cleanup_jobs_dir(config.jobs_dir())` một lần khi server khởi động
  (trong `main()` trước `uvicorn.run`), log kết quả 1 dòng. Bọc try/except —
  GC lỗi không được chặn server chạy.
- Tests (`tests/test_core.py` hoặc file mới `tests/test_janitor.py`):
  - xóa job quá hạn; giữ job mới
  - không xóa job `status == "running"` dù cũ
  - vượt `max_total_bytes` → xóa cũ nhất trước, tôn trọng `keep_newest`
  - status.json hỏng/không phải dict → skip, không xóa
  - thư mục lạ trong jobs/ (không có status.json) → không xóa
- README: cập nhật mục jobs dir — từ "xóa thủ công" sang auto-GC policy.

## Task 2 — Integration test qua uvicorn thật

Mục tiêu: chứng minh `_security_guard` hoạt động trên socket thật (TestClient
đi qua cùng ASGI stack nhưng không qua TCP/uvicorn header pipeline).

- File mới `tests/test_server_live.py`, pytest:
  - boot `uvicorn.Server(Config(app, host="127.0.0.1", port=<free>, log_level="error"))`
    trong thread daemon; đợi port accept (tối đa ~5s); chạy asserts; shutdown.
  - Assert: GET `/` với Host 127.0.0.1 → 200 + security headers;
    request Host `evil.example` → 403; POST `/api/jobs` với
    `Origin: https://evil.example` → 403; `sec-fetch-site: cross-site` → 403.
  - Dùng `httpx` (đã là dep của fastapi testclient) hoặc urllib; header Host
    ghi đè qua `headers={"Host": "evil.example"}`.
  - Server fixture function-scope, teardown gọi `server.should_exit = True`
    + join. Không mở browser (gọi uvicorn trực tiếp, không qua `main()`).

## Task 3 — Punctuation acceptance trên macOS x86_64

Chạy thật trên máy này (không phải subagent):

- `uv run pytest -m model tests/test_punctuate.py::test_real_punctuation_model_contract -v`
  (lần đầu tải ~110 MB model vào data dir thật — hành vi được thiết kế của app).
- `HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py`.
- Ghi evidence vào `docs/11` cột "macOS x86_64" cho PR-14 (và PR-12 nếu full
  suite chạy lại xanh). PR-13 giữ BLOCKED (fixture riêng tư — không bịa).
- onnxruntime 1.23.2 (mới pin) phải load được model — đây cũng là verify cho
  pin version trên Intel Mac.

## Task 4 — Windows static audit (không cần máy Windows)

Read-only review, output là checklist verify cho máy Windows thật:

- `config.data_dir()` nhánh `os.name == "nt"` (APPDATA fallback),
  `.bat` (không dấu, codepage), `install.bat`/`run.bat` đường dẫn `%USERPROFILE%`,
  mọi `Path`/`open`/`subprocess` trong app — tìm giả định POSIX lén.
- `server.py`: `_free_port`, `webbrowser.open`, middleware Host trên
  `localhost`/`127.0.0.1` (Windows thường resolve localhost → ::1 — kiểm tra
  `::1` nằm trong `_ALLOWED_HOSTS`).
- Output: bổ sung "Windows verification checklist" vào `docs/03-tasks.md`
  phần Task 14 hoặc file checklist riêng nếu phù hợp hơn.

## Task 5 — WER scaffolding dry-run

- `uv run python scripts/eval_wer.py` không có `eval/sample.*` → phải báo
  hướng dẫn rõ ràng, không traceback. Nếu output xấu → sửa message (không đổi logic).

## Không làm (ghi rõ lý do)

- Verify Windows thật / file dài trên Windows: không có máy.
- WER thật + diarization trên audio thật: cần sample người dùng cung cấp.
- PR-13 eval_punctuation: cần fixture `eval/punctuation_*` riêng tư.
