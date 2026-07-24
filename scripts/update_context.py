#!/usr/bin/env python3
"""Tái tạo phần động của CLAUDE.md và AGENTS.md từ trạng thái repo hiện tại.

Chạy tự động khi commit vào main (qua git hook + Claude Code hook).
Cũng có thể chạy thủ công: python3 scripts/update_context.py
"""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
DOCS = REPO / "docs"
CLAUDE_MD = REPO / "CLAUDE.md"
AGENTS_MD = REPO / "AGENTS.md"
APP_DIR = REPO / "app"
TASKS_FILE = DOCS / "03-tasks.md"


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


def get_app_files() -> str:
    if not APP_DIR.exists():
        return "_Chưa có code trong app/._"
    files = sorted(
        p.name for p in APP_DIR.iterdir()
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
    files = get_app_files()

    risks_block = f"\n\n**Rủi ro / việc treo đang mở:**\n{risks}" if risks.strip() else ""
    return f"""\
## Trạng thái hiện tại

> _Phần này tự động cập nhật khi commit vào main._

**Tiến độ:** {done}/{total} task xong 🟢 | {in_progress} đang chạy 🔵 | {todo} chưa làm ⚪

**Module đã có trong `app/`:** {files}

**Bảng tasks (xem chi tiết: [docs/03-tasks.md](docs/03-tasks.md)):**

{table}{risks_block}"""


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


# ── Cập nhật AGENTS.md (chỉ thay block status) ───────────────────────────────

_AGENTS_START = "<!-- status-block: start -->"
_AGENTS_END   = "<!-- status-block: end -->"


def build_agents_status_section() -> str:
    done, in_progress, todo = count_task_states()
    total = done + in_progress + todo
    table = get_task_table()
    risks = get_open_risks()
    files = get_app_files()

    risks_block = f"\n\n**Open risks / blockers:**\n{risks}" if risks.strip() else ""
    return f"""\
## Current status

**Progress:** {done}/{total} tasks done 🟢 | {in_progress} in-progress 🔵 | {todo} not started ⚪

**App modules in `app/`:**
{files}

**Task table:**

{table}{risks_block}"""


def update_agents_md():
    if not AGENTS_MD.exists():
        print("  ✗ Không tìm thấy AGENTS.md")
        return

    text = AGENTS_MD.read_text(encoding="utf-8")
    new_section = f"{_AGENTS_START}\n{build_agents_status_section()}\n{_AGENTS_END}"

    if _AGENTS_START in text and _AGENTS_END in text:
        text = re.sub(
            re.escape(_AGENTS_START) + r".*?" + re.escape(_AGENTS_END),
            new_section,
            text,
            flags=re.DOTALL,
        )
        AGENTS_MD.write_text(text, encoding="utf-8")
        print("  ✓ AGENTS.md đã cập nhật")
    else:
        print("  ✗ AGENTS.md thiếu markers <!-- status-block: start/end --> — bỏ qua")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Đang cập nhật context files...")
    update_claude_md()
    update_agents_md()
    print("Xong.")
