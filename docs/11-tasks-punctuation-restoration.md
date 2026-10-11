# Punctuation Restoration — verification tracker

**Spec:** `docs/dev/specs/2026-07-19-punctuation-restoration-design.md`

| ID | Automated evidence | macOS arm64 | macOS x86_64 | Windows x64 |
|---|---|---|---|---|
| PR-01..PR-05 | `tests/test_punctuate.py` | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-06..PR-07 | model smoke + hash | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-08..PR-09 | API/UI/partial tests | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-10 | `uv tree` no torch/tensorflow | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-11 | notices/README review | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-12 | ruff + full pytest | PASS (2026-07-19) | PASS (2026-09-18) | — |
| PR-13 | `scripts/eval_punctuation.py` | BLOCKED: cần fixture | BLOCKED: cần fixture | BLOCKED: cần fixture |
| PR-14 | real model smoke | PASS (2026-07-19, offline cache) | PASS (2026-09-18, offline cache) | — |

Chỉ thay `—`/`BLOCKED` bằng PASS khi có command, ngày, máy và output thật được ghi
bên dưới bảng. Không suy ra PASS của nền tảng khác.

## Evidence log (macOS arm64)

- Date: 2026-07-19
- Machine: macOS arm64 (local worktree `.worktrees/vitranscript-impl`)
- Unit suite: `uv run pytest tests/ -v` (default excludes `@pytest.mark.model`)
- Model smoke (online then offline):
  - `uv run pytest -m model tests/test_punctuate.py::test_real_punctuation_model_contract -v` → PASS (~13s first run)
  - `HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py` → `"Hà Nội là thủ đô Việt Nam. Tôi yêu nó."`
- Pin: revision `a7754d037f4a9e29f7f3224f27acb60149eab874`, sha256 `67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa`
- Dependency gate: no `torch` / `tensorflow` in `uv tree`
- PR-13: no private `eval/punctuation_*.{json,txt}` fixture in this session

- Ngày: 2026-07-23 — `_apply_case` không còn dùng `str.capitalize()`. Một token đã
  được viết hoa toàn bộ ở pass refine trước (`"WHO"` qua `$TRANSFORM_CASE_UPPER`)
  giờ giữ nguyên `"WHO"` khi gặp `$TRANSFORM_CASE_CAPITAL` ở pass sau, thay vì bị
  hạ xuống `"Who"` như hành vi cũ. Vì vậy vòng lặp refine đôi khi kết thúc sớm
  hơn một pass so với trước. Đây là ngữ nghĩa đúng và là chủ ý.
  Bằng chứng rằng output thực tế không đổi hiện chỉ là một lần chạy smoke test
  10 từ (`HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py` →
  `"Hà Nội là thủ đô Việt Nam. Tôi yêu nó."`), KHÔNG phải một bộ corpus — nói rõ
  để tránh hiểu nhầm đây là kiểm chứng đầy đủ.

## Evidence log (macOS x86_64)

- Date: 2026-09-18
- Machine: macOS x86_64 (Darwin x86_64), `onnxruntime==1.23.2` (pin `<1.24` vì
  1.25+ không còn wheel mac x86_64), Python 3.12.14
- Unit suite: `uv run pytest tests/ -q` → **91 passed, 1 deselected** (bao gồm
  `tests/test_punctuate.py`, API/UI tests, `tests/test_server_live.py`)
- Model smoke (online + offline, dùng HF cache đã có sẵn):
  - `uv run pytest -m model tests/test_punctuate.py::test_real_punctuation_model_contract -v` → PASS (7.25s)
  - `HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py` →
    `"Hà Nội là thủ đô Việt Nam. Tôi yêu nó."` — output khớp y hệt arm64
- Lint: `uv run ruff check .` clean
- Pin verify: revision `a7754d037f4a9e29f7f3224f27acb60149eab874`, sha256
  `67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa` (model
  contract test kiểm cả hash)
- Dependency gate: `uv tree` không có `torch` / `tensorflow` (0 match)
- Notices: `THIRD_PARTY_NOTICES.md` đã liệt kê ViBERT-CAPU, revision pin,
  license CC-BY-SA-4.0 — review lại đúng trên máy này
- PR-13: vẫn BLOCKED — chưa có private `eval/punctuation_*.{json,txt}` fixture
- Windows x64: chưa verify (không có máy Windows trong phiên)
