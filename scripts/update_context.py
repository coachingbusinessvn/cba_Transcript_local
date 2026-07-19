#!/usr/bin/env python3
"""Tái tạo phần động của CLAUDE.md và AGENTS.md từ trạng thái repo hiện tại.

Chạy tự động khi commit vào main (qua git hook + Claude Code hook).
Cũng có thể chạy thủ công: python3 scripts/update_context.py
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent
DOCS = REPO / "docs"
CLAUDE_MD = REPO / "CLAUDE.md"
AGENTS_MD = REPO / "AGENTS.md"
WORKTREE = REPO / ".worktrees" / "vitranscript-impl"
# Ưu tiên file tasks từ worktree (cập nhật hơn), fallback về main docs
_wt_tasks = WORKTREE / "docs" / "03-tasks.md"
TASKS_FILE = _wt_tasks if _wt_tasks.exists() else DOCS / "03-tasks.md"


def git(*args) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return r.stdout.strip()


def get_task_table() -> str:
    if not TASKS_FILE.exists():
        return "_Chưa có file tasks._"
    text = TASKS_FILE.read_text(encoding="utf-8")
    # Lấy bảng trạng thái (dòng có |) từ phần đầu của file
    lines, in_table = [], False
    for line in text.splitlines():
        if line.startswith("| #"):
            in_table = True
        if in_table:
            if line.startswith("|"):
                lines.append(line)
            elif lines:
                break
    return "\n".join(lines) if lines else "_Không tìm thấy bảng tasks._"


def count_task_states() -> tuple[int, int, int]:
    """Trả về (xong, dang_lam, chua_lam)."""
    if not TASKS_FILE.exists():
        return 0, 0, 0
    text = TASKS_FILE.read_text(encoding="utf-8")
    done = text.count("🟢")
    in_progress = text.count("🔵")
    todo = text.count("⚪")
    return done, in_progress, todo


def get_recent_commits(n: int = 5) -> str:
    log = git("log", "--oneline", f"-{n}")
    if not log:
        return "_Chưa có commit._"
    return "\n".join(f"- `{line}`" for line in log.splitlines())


def get_worktree_app_files() -> str:
    app_dir = WORKTREE / "app"
    if not app_dir.exists():
        return "_Worktree chưa có code._"
    files = sorted(
        p.name for p in app_dir.iterdir()
        if p.suffix == ".py" and p.name != "__init__.py"
    )
    return ", ".join(f"`{f}`" for f in files) if files else "_Trống._"


def get_open_risks() -> str:
    if not TASKS_FILE.exists():
        return ""
    text = TASKS_FILE.read_text(encoding="utf-8")
    # Lấy section "Việc treo / rủi ro đang mở"
    match = re.search(r"## Việc treo.*?(?=\n## |\Z)", text, re.DOTALL)
    if not match:
        return ""
    lines = [
        ln for ln in match.group(0).splitlines()
        if ln.strip().startswith("- [ ]")  # chỉ lấy mục chưa xong
    ]
    return "\n".join(lines[:6]) if lines else "_Không còn mục treo._"


def build_status_section() -> str:
    done, in_progress, todo = count_task_states()
    total = done + in_progress + todo
    table = get_task_table()
    risks = get_open_risks()
    commits = get_recent_commits()
    files = get_worktree_app_files()

    risks_block = f"\n\n**Rủi ro / việc treo đang mở:**\n{risks}" if risks.strip() else ""
    return f"""\
## Trạng thái hiện tại

> _Phần này tự động cập nhật khi commit vào main._

**Tiến độ:** {done}/{total} task xong 🟢 | {in_progress} đang chạy 🔵 | {todo} chưa làm ⚪

**Module đã có trong `app/`:** {files}

**Bảng tasks (xem chi tiết: [docs/03-tasks.md](docs/03-tasks.md)):**

{table}{risks_block}

**5 commit gần nhất:**

{commits}"""


# ── Cập nhật CLAUDE.md ────────────────────────────────────────────────────────

_START = "<!-- auto-update: start -->"
_END   = "<!-- auto-update: end -->"


def update_claude_md():
    if not CLAUDE_MD.exists():
        print("  ✗ Không tìm thấy CLAUDE.md")
        return

    text = CLAUDE_MD.read_text(encoding="utf-8")
    new_section = f"{_START}\n{build_status_section()}\n{_END}"

    if _START in text and _END in text:
        text = re.sub(
            re.escape(_START) + r".*?" + re.escape(_END),
            new_section,
            text,
            flags=re.DOTALL,
        )
    else:
        # Lần đầu: thay thế section ## Trạng thái hiện tại cũ (nếu có)
        text = re.sub(
            r"## Trạng thái hiện tại[^\n]*\n.*?(?=\n## |\Z)",
            new_section + "\n\n",
            text,
            flags=re.DOTALL,
        )

    CLAUDE_MD.write_text(text, encoding="utf-8")
    print("  ✓ CLAUDE.md đã cập nhật")


# ── Tái tạo AGENTS.md ─────────────────────────────────────────────────────────

def write_agents_md():
    done, in_progress, todo = count_task_states()
    total = done + in_progress + todo
    table = get_task_table()
    commits = get_recent_commits(3)
    files = get_worktree_app_files()

    content = f"""\
# ViTranscript — Agent Context

> Auto-generated. Do not edit manually — regenerated on every commit to main.
> Canonical detail docs: `docs/01-bai-toan.md`, `docs/02-plan.md`, `docs/03-tasks.md`.

## What this project is

Local-first Vietnamese transcription app (Mac/Windows). Input: audio/video file.
Output: DOCX/XLSX/SRT/TXT with timestamps and speaker labels. Fully offline after first model download.

## Repository layout

```
docs/              Technical docs (no code here)
  01-bai-toan.md   Problem statement, tech decisions, acceptance criteria
  02-plan.md       Per-task plan with full code, interfaces, verify steps
  03-tasks.md      Task tracking table (status, notes, WER results)
.worktrees/
  vitranscript-impl/   ALL CODE lives here (git worktree branch)
CLAUDE.md          AI-context file (auto-updated)
AGENTS.md          This file (auto-updated)
```

**Important:** to work with code, always use `.worktrees/vitranscript-impl/` path.

## Tech stack

| Component | Library | Constraint |
|---|---|---|
| Transcript | faster-whisper (CTranslate2, CPU int8) | NO PyTorch |
| Diarization | sherpa-onnx (pyannote seg3 ONNX + eres2net) | No HF token needed |
| Web UI | FastAPI + single static HTML | localhost 127.0.0.1 only |
| Install | `uv` (self-installs Python 3.12) | |
| Python | `>=3.10,<3.13` | |

## Current implementation status ({done}/{total} tasks done)

{table}

**App modules present:** {files}

**Recent commits:**

{commits}

## Hard constraints (never violate)

- NO dependency that pulls PyTorch or TensorFlow
- v1: **one job at a time** — server returns HTTP 409 if a job is already running
- Server binds `127.0.0.1` only — never `0.0.0.0`
- `"speaker-recongition-models"` in diarization URL — intentional typo from upstream, do NOT "fix"
- `.bat` scripts: no Vietnamese diacritics (Windows codepage issues)
- `names` dict keys are always strings: `"0"`, `"1"`, ... (consistent across export/server/UI)

## Dev commands (run from `.worktrees/vitranscript-impl/`)

```bash
uv sync                           # install/update deps
uv run ruff check .               # lint (must be clean before commit)
uv run pytest tests/ -v           # 8 unit tests
uv run python -m app.server       # start app (auto-opens browser at port 8756+)
uv run python scripts/smoke_e2e.py    # macOS smoke test
uv run python scripts/eval_wer.py     # WER measurement (needs eval/sample.*)
```

## Commit convention

Each task: code → `uv run ruff check .` → verify → commit.
Trailer line: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
"""
    AGENTS_MD.write_text(content, encoding="utf-8")
    print("  ✓ AGENTS.md đã cập nhật")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Đang cập nhật context files...")
    update_claude_md()
    write_agents_md()
    print("Xong.")
