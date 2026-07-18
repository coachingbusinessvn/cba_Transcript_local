# Plan: Chọn lại người nói cho từng dòng transcript

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mỗi dòng transcript trong bảng xem trước có dropdown chọn lại người nói; file xuất ra (DOCX/XLSX/SRT/TXT) phản ánh chỉnh sửa. Spec đã chốt: [06-spec-speaker-reselect.md](06-spec-speaker-reselect.md).

**Architecture:** Client-side only. UI thay ô text "Người nói" bằng `<select>` (option = speaker phát hiện được, tính một lần tại `showResults`); đổi lựa chọn cập nhật thẳng `sentences[i].speaker` trong browser. Khi export, client gửi kèm map `speakers: {"<index>": id}` chỉ chứa dòng thay đổi; server áp override best-effort vào bản sao sentences trước khi dựng file. Không endpoint mới, không persist.

**Tech Stack:** Không dependency mới. Vanilla JS trong `index.html`, một hàm thuần + 3 dòng trong `app/server.py`.

## Global Constraints

- Kế thừa Global Constraints của [02-plan.md](02-plan.md); commit trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Override là **best-effort**: entry không hợp lệ (index ngoài biên, speaker lạ, kiểu rác) bị bỏ qua êm, KHÔNG trả 400
- **Xung đột biết trước:** [04-plan-long-audio.md](04-plan-long-audio.md) Task 5 cũng sửa `export_job` (đổi cổng kiểm tra `status`). Hai thay đổi độc lập về logic; plan nào chạy sau thì giữ nguyên thay đổi của plan chạy trước (conflict chỉ ở mức dòng kề nhau)

---

### Task 1: Server — áp speaker override khi export

**Files:**
- Modify: `app/server.py` (thêm `_apply_speaker_overrides`, gọi trong `export_job`)
- Test: `tests/test_core.py` (thêm 2 test)

**Interfaces:**
- Consumes: `Sentence(start, end, text, speaker)` từ `app/segment.py:13-18`; body export hiện tại `{format, names}`
- Produces: `server._apply_speaker_overrides(sentences: list[Sentence], overrides: dict) -> None` (sửa tại chỗ); `export_job` đọc thêm `body["speakers"]`. Task 2 (UI) gửi key này.

- [ ] **Step 1: Viết 2 test fail**

Thêm vào `tests/test_core.py`:

```python
def test_apply_speaker_overrides():
    from app.segment import Sentence
    from app.server import _apply_speaker_overrides

    sents = [Sentence(0, 1, "a", 0), Sentence(1, 2, "b", 1), Sentence(2, 3, "c", 1)]
    _apply_speaker_overrides(sents, {
        "2": 0,        # hợp lệ → đổi
        "0": 5,        # speaker 5 không tồn tại → bỏ qua
        "99": 1,       # index ngoài biên → bỏ qua
        "bad": 1,      # index rác → bỏ qua
        "1": "x",      # speaker rác → bỏ qua
    })
    assert [s.speaker for s in sents] == [0, 1, 0]
    # None và rỗng không đổ vỡ
    _apply_speaker_overrides(sents, None)
    _apply_speaker_overrides(sents, {})


def test_export_srt_with_speaker_override(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app import config, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    job_id = "spkoverride01"
    (tmp_path / "jobs" / job_id).mkdir(parents=True)
    server.JOBS[job_id] = {
        "status": "done", "filename": "hop.mp3",
        "result": {"sentences": [
            {"start": 0.0, "end": 1.0, "text": "Xin chào.", "speaker": 0},
            {"start": 1.0, "end": 2.0, "text": "Chào bạn.", "speaker": 1},
        ], "duration": 2.0, "num_speakers": 2, "extracted_audio": None, "model": "x"},
    }
    try:
        c = TestClient(server.app)
        r = c.post(f"/api/jobs/{job_id}/export",
                   json={"format": "srt", "speakers": {"1": 0}})
        assert r.status_code == 200
        srt = (tmp_path / "jobs" / job_id / "hop.srt").read_text(encoding="utf-8")
        assert "Người nói 1: Chào bạn." in srt  # dòng 2 đã đổi từ speaker 1 → 0
    finally:
        server.JOBS.pop(job_id, None)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py -k override -v`
Expected: FAIL — `ImportError: cannot import name '_apply_speaker_overrides'`

- [ ] **Step 3: Sửa `app/server.py`**

(a) Thêm hàm (đặt trên `export_job`):

```python
def _apply_speaker_overrides(sentences: list[Sentence], overrides: dict | None) -> None:
    """Áp chỉnh sửa người nói từ client (best-effort, entry không hợp lệ bỏ qua êm)."""
    if not overrides:
        return
    valid = {s.speaker for s in sentences if s.speaker is not None}
    for k, v in overrides.items():
        try:
            i, spk = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(sentences) and spk in valid and sentences[i].speaker is not None:
            sentences[i].speaker = spk
```

(b) Trong `export_job`, ngay sau dòng `sentences = [Sentence(**s) for s in job["result"]["sentences"]]` thêm:

```python
    _apply_speaker_overrides(sentences, body.get("speakers"))
```

- [ ] **Step 4: Chạy toàn bộ test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: tất cả pass (+2 so với trước), ruff sạch

- [ ] **Step 5: Commit**

```bash
git add app/server.py tests/test_core.py
git commit -m "feat: export ap speaker override tu client

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: UI — dropdown chọn người nói mỗi dòng

**Files:**
- Modify: `app/static/index.html` (state, `renderPreview`, `showResults`, body export, CSS)

**Interfaces:**
- Consumes: key `speakers` trong body export (Task 1); `speakerLabel(idx)`, `renderPreview()`, `showResults(job)`, `names` sẵn có
- Produces: mỗi dòng có speaker → `<select class="spk-select">`; `collectSpeakerOverrides() -> {"<index>": id}` chỉ chứa dòng khác kết quả gốc

- [ ] **Step 1: Thêm state** — cạnh `let names = {};` (dòng ~377):

```js
      let speakerIds = [];        // speaker phát hiện được — tính 1 lần tại showResults
      let originalSpeakers = [];  // snapshot để tính override khi export
```

- [ ] **Step 2: Sửa `renderPreview`** — thay 2 dòng tạo `tdS` (hiện tại: `tdS.className = "spk"; tdS.textContent = speakerLabel(s.speaker);`) bằng:

```js
          const tdS = document.createElement("td");
          tdS.className = "spk";
          if (s.speaker === null || s.speaker === undefined || !speakerIds.length) {
            tdS.textContent = speakerLabel(s.speaker);
          } else {
            const sel = document.createElement("select");
            sel.className = "spk-select";
            speakerIds.forEach((id) => {
              const opt = document.createElement("option");
              opt.value = String(id);
              opt.textContent = speakerLabel(id);
              if (id === s.speaker) opt.selected = true;
              sel.appendChild(opt);
            });
            sel.addEventListener("change", () => { s.speaker = Number(sel.value); });
            tdS.appendChild(sel);
          }
```

(Lưu ý: `list.forEach((s) => …)` giữ nguyên — `s` là reference vào `sentences`, mutate là đủ.)

- [ ] **Step 3: Sửa `showResults`** — sau `sentences = result.sentences || [];` thêm:

```js
        originalSpeakers = sentences.map((s) => s.speaker);
        const seenIds = new Set();
        speakerIds = [];
        sentences.forEach((s) => {
          if (s.speaker === null || s.speaker === undefined) return;
          if (!seenIds.has(s.speaker)) { seenIds.add(s.speaker); speakerIds.push(s.speaker); }
        });
        speakerIds.sort((a, b) => Number(a) - Number(b));
```

- [ ] **Step 4: Thêm `collectSpeakerOverrides`** (cạnh `collectNames`) và nối vào body export — trong handler export, đổi `const body = { format: fmt, names: collectNames() };` thành:

```js
      function collectSpeakerOverrides() {
        const out = {};
        sentences.forEach((s, i) => {
          if (s.speaker === null || s.speaker === undefined) return;
          if (originalSpeakers[i] !== s.speaker) out[String(i)] = s.speaker;
        });
        return out;
      }
```

```js
        const body = { format: fmt, names: collectNames(), speakers: collectSpeakerOverrides() };
```

- [ ] **Step 5: CSS** — thêm vào `<style>` (cạnh `.spk`):

```css
    .spk-select {
      width: 100%; padding: 4px 6px; border-radius: 6px;
      border: 1px solid #d5d9e0; background: transparent; font: inherit; font-size: 13px;
    }
```

- [ ] **Step 6: Verify**

Run:
```bash
uv run python -c "
from fastapi.testclient import TestClient
from app.server import app
html = TestClient(app).get('/').text
assert 'collectSpeakerOverrides' in html and 'spk-select' in html
print('UI OK')"
```
Expected: `UI OK`

Duyệt tay: chạy `uv run python -m app.server`, transcript file ngắn có 2 người nói → mỗi dòng có dropdown; đổi speaker 1 dòng; đổi tên "Người nói 1" → nhãn dropdown cập nhật; export SRT → dòng đã đổi mang tên mới.

- [ ] **Step 7: Commit**

```bash
git add app/static/index.html
git commit -m "feat: UI dropdown chon lai nguoi noi tung dong transcript

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Tài liệu

**Files:**
- Modify: `docs/08-tasks-speaker-reselect.md` (trạng thái 🟢 khi xong), `README.md`

- [ ] **Step 1: README** — thêm vào mục tính năng:

```markdown
- Sửa nhầm lẫn người nói: mỗi dòng transcript có dropdown chọn lại người nói trước khi xuất file (chỉnh sửa sống trong trang — refresh sẽ mất).
```

- [ ] **Step 2: Commit**

```bash
git add README.md docs/08-tasks-speaker-reselect.md
git commit -m "docs: tinh nang chon lai nguoi noi

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
