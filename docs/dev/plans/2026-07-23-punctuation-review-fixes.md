# Punctuation Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa 5 defect thật được phát hiện khi review plan `2026-07-19-punctuation-restoration.md`, không thay đổi hành vi phục hồi dấu câu đã nghiệm thu.

**Architecture:** Toàn bộ thay đổi nằm trong `app/punctuate.py` (case transform + xác minh artifact + tài liệu vòng lặp refinement), `tests/test_punctuate.py` (test contract chặt hơn) và `scripts/eval_punctuation.py` (map boundary theo index thay vì timestamp). Không đổi API pipeline/server/UI, không đổi pin model.

**Tech Stack:** Python 3.10–3.12, ONNX Runtime CPU, Hugging Face `tokenizers`, NumPy, pytest, ruff.

## Global Constraints

- Chạy mọi lệnh từ `.worktrees/vitranscript-impl/`.
- KHÔNG thêm dependency mới; KHÔNG kéo PyTorch/TensorFlow.
- KHÔNG đổi `PUNCTUATION_MODEL` (repo_id, revision, filename, size, sha256, license).
- Invariant tuyệt đối giữ nguyên: `restore()` không được đổi số `Word`, `start`, `end`,
  hay chính tả — chỉ hoa/thường và thêm `. , : ?`.
- Mọi lỗi trong `restore()` vẫn phải fallback về transcript gốc, không raise ra pipeline.
- Server chỉ bind `127.0.0.1`; 1 job tại một thời điểm.
- Giữ nguyên URL upstream có typo `speaker-recongition-models`.
- Text tiếng Việt trong code/UI giữ dấu; `.bat` không dấu (task này không chạm `.bat`).
- Mỗi task theo TDD: test đỏ → implementation tối thiểu → test xanh → `uv run ruff check .` sạch → commit.
- Mỗi commit kết thúc bằng trailer:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Test mặc định KHÔNG được tải model (`addopts = "-m 'not model'"` đã có sẵn).
- Không đánh dấu PASS cho nền tảng chưa thật sự chạy.

## File map

### Modify

- `app/punctuate.py` — `_apply_case`, `_ensure_model_dir`/`_verify_artifact`, comment vòng refinement.
- `tests/test_punctuate.py` — thêm/siết test cho cả 5 fix.
- `scripts/eval_punctuation.py` — `sentence_boundaries()` map theo index; body vào `main()`.
- `docs/11-tasks-punctuation-restoration.md` — bỏ env var thừa khỏi command evidence.
- `docs/dev/plans/2026-07-19-punctuation-restoration.md` — phụ lục amendments.

Không tạo file mới.

---

## Task 1: `$TRANSFORM_CASE_CAPITAL` không phá casing giữa từ

**Files:**

- Modify: `app/punctuate.py:141-152`
- Test: `tests/test_punctuate.py` (hàm `test_case_actions_are_exact_and_unsupported_actions_keep_text`)

**Interfaces:**

- Consumes: `_apply_case(token: str, action: str) -> str` (đã có).
- Produces: cùng chữ ký; chỉ đổi ngữ nghĩa hai action `$TRANSFORM_CASE_CAPITAL` và
  `$TRANSFORM_CASE_CAPITAL_1` — chúng chỉ đổi đúng MỘT ký tự, không đụng phần còn lại.

**Bối cảnh:** `str.capitalize()` hạ thấp toàn bộ phần đuôi. `output_core` giữ casing gốc
từ ASR/glossary, nên `"iPhone"` → `"Iphone"` và `"VNExpress"` → `"Vnexpress"`.
`_invariants_hold()` dùng `casefold()` nên KHÔNG bắt được lỗi này. README hứa bước này
"chỉ đổi viết hoa" — phải đúng theo nghĩa đen.

- [ ] **Step 1: Thêm assertion đỏ vào test case action**

Trong `tests/test_punctuate.py`, thêm vào cuối hàm
`test_case_actions_are_exact_and_unsupported_actions_keep_text` (giữ nguyên các assert đã có):

```python
    # Chỉ đổi đúng một ký tự — casing giữa từ do ASR/glossary tạo ra phải sống sót.
    assert _apply_case("iPhone", "$TRANSFORM_CASE_CAPITAL") == "IPhone"
    assert _apply_case("VNExpress", "$TRANSFORM_CASE_CAPITAL") == "VNExpress"
    assert _apply_case("iphoneX", "$TRANSFORM_CASE_CAPITAL_1") == "iPhoneX"
    assert _apply_case("", "$TRANSFORM_CASE_CAPITAL") == ""
    assert _apply_case("a", "$TRANSFORM_CASE_CAPITAL_1") == "a"
```

- [ ] **Step 2: Chạy test và xác nhận đỏ**

```bash
uv run pytest tests/test_punctuate.py::test_case_actions_are_exact_and_unsupported_actions_keep_text -q
```

Expected: FAIL — `assert 'Iphone' == 'IPhone'`.

- [ ] **Step 3: Sửa `_apply_case`**

Thay thân hàm `_apply_case` trong `app/punctuate.py` bằng:

```python
def _apply_case(token: str, action: str) -> str:
    # Mỗi action chỉ được đổi đúng phần ký tự nó mô tả. Dùng str.capitalize() sẽ
    # hạ thấp phần đuôi và phá casing có sẵn ("iPhone" -> "Iphone"), mà invariant
    # casefold() không phát hiện được.
    if action == "$TRANSFORM_CASE_LOWER":
        return token.lower()
    if action == "$TRANSFORM_CASE_UPPER":
        return token.upper()
    if action == "$TRANSFORM_CASE_CAPITAL" and token:
        return token[0].upper() + token[1:]
    if action == "$TRANSFORM_CASE_CAPITAL_1" and len(token) > 1:
        return token[:1] + token[1].upper() + token[2:]
    if action == "$TRANSFORM_CASE_UPPER_-1" and token:
        return token[:-1].upper() + token[-1]
    return token
```

- [ ] **Step 4: Chạy test và lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
```

Expected: PASS toàn bộ file test, ruff sạch. Các assert cũ
(`"hà"` → `"Hà"`, `"iphone"` → `"iPhone"`) vẫn phải xanh.

- [ ] **Step 5: Commit**

```bash
git add app/punctuate.py tests/test_punctuate.py
git commit -m "fix: case transform khong pha casing giua tu" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: Xác minh SHA-256 artifact đã cache trước khi nạp runtime

**Files:**

- Modify: `app/punctuate.py:38-66`
- Test: `tests/test_punctuate.py` (thêm 1 test mới sau `test_ensure_model_dir_rejects_wrong_hash`)

**Interfaces:**

- Consumes: `config.punctuation_is_downloaded()`, `config.sha256_file(path)`,
  `config.punctuation_manifest_path()`, `_snapshot_download(**kwargs)` (đã có).
- Produces: `_verify_artifact(root: Path) -> None` — raise `RuntimeError` nếu sai
  size/SHA-256/thiếu file. `_ensure_model_dir() -> Path` giữ nguyên chữ ký.

**Bối cảnh:** Hiện `_ensure_model_dir()` return sớm khi `punctuation_is_downloaded()` True,
mà hàm đó chỉ so size + manifest do chính app ghi. File 110 MB hỏng sau khi ghi (đúng size,
sai bytes) sẽ lọt thẳng vào ONNX Runtime. `_ensure_model_dir()` chỉ được gọi từ
`_load_runtime()` vốn cache một lần mỗi process, nên đọc lại 110 MB để tính SHA là chi phí
một lần, chấp nhận được.

- [ ] **Step 1: Viết test đỏ cho file cache bị hỏng**

Thêm vào `tests/test_punctuate.py`, ngay sau `test_ensure_model_dir_rejects_wrong_hash`:

```python
def test_ensure_model_dir_rejects_corrupted_cached_file(monkeypatch, tmp_path):
    from app import config, punctuate

    payload = b"abc"
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", len(payload))
    monkeypatch.setitem(
        config.PUNCTUATION_MODEL, "sha256", hashlib.sha256(payload).hexdigest()
    )
    root = config.punctuation_dir()
    # Đúng size, sai bytes — manifest hợp lệ nên punctuation_is_downloaded() True.
    (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(b"xyz")
    config.punctuation_manifest_path().write_text(
        json.dumps({
            "revision": config.PUNCTUATION_MODEL["revision"],
            "sha256": config.PUNCTUATION_MODEL["sha256"],
        }),
        encoding="utf-8",
    )

    def forbidden_download(**kwargs):
        raise AssertionError("không được tải lại khi cache đã đầy đủ")

    monkeypatch.setattr(punctuate, "_snapshot_download", forbidden_download)
    with pytest.raises(RuntimeError, match="SHA-256"):
        punctuate._ensure_model_dir()
```

- [ ] **Step 2: Chạy test và xác nhận đỏ**

```bash
uv run pytest tests/test_punctuate.py::test_ensure_model_dir_rejects_corrupted_cached_file -q
```

Expected: FAIL — không có exception nào được raise (`_ensure_model_dir` return sớm).

- [ ] **Step 3: Tách `_verify_artifact` và bỏ đường return không xác minh**

Thay toàn bộ `_ensure_model_dir` trong `app/punctuate.py` bằng:

```python
def _verify_artifact(root: Path) -> None:
    model_path = root / config.PUNCTUATION_MODEL["filename"]
    if model_path.stat().st_size != config.PUNCTUATION_MODEL["size"]:
        raise RuntimeError("Model dấu câu sai kích thước")
    if config.sha256_file(model_path) != config.PUNCTUATION_MODEL["sha256"]:
        raise RuntimeError("Model dấu câu sai SHA-256")
    for relative in _REQUIRED_FILES:
        if not (root / relative).is_file():
            raise RuntimeError(f"Model dấu câu thiếu file runtime: {relative}")


def _write_manifest(root: Path) -> None:
    manifest = {
        "revision": config.PUNCTUATION_MODEL["revision"],
        "sha256": config.PUNCTUATION_MODEL["sha256"],
    }
    tmp = root / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, config.punctuation_manifest_path())


def _ensure_model_dir() -> Path:
    root = config.punctuation_dir()
    if not config.punctuation_is_downloaded():
        _snapshot_download(
            repo_id=config.PUNCTUATION_MODEL["repo_id"],
            revision=config.PUNCTUATION_MODEL["revision"],
            local_dir=str(root),
            allow_patterns=list(_REQUIRED_FILES),
        )
    # Manifest chỉ ghi revision + sha kỳ vọng, không phát hiện file hỏng sau khi ghi.
    # Hàm này chỉ chạy một lần mỗi process (qua cache của _load_runtime), nên luôn
    # băm lại artifact trước khi đưa cho ONNX Runtime.
    _verify_artifact(root)
    _write_manifest(root)
    return root
```

- [ ] **Step 4: Chạy test và lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
```

Expected: PASS. Hai test cũ
(`test_ensure_model_dir_verifies_hash_and_writes_manifest`,
`test_ensure_model_dir_rejects_wrong_hash`) phải vẫn xanh — test thứ hai vẫn kỳ vọng
`punctuation_manifest_path()` không tồn tại vì `_verify_artifact` chạy trước `_write_manifest`.

- [ ] **Step 5: Commit**

```bash
git add app/punctuate.py tests/test_punctuate.py
git commit -m "fix: bam lai SHA-256 artifact dau cau da cache" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: Ghi rõ và test vòng lặp refinement 3 pass

**Files:**

- Modify: `app/punctuate.py:320-362` (chỉ thêm comment)
- Test: `tests/test_punctuate.py` (thêm 2 test mới sau `test_restore_empty_does_not_load_runtime`)

**Interfaces:**

- Consumes: `punctuate.restore(words, *, progress_cb=None) -> PunctuationResult`,
  `punctuate._predict_actions(pieces, runtime, progress_cb=None) -> tuple[list[str], int]`.
- Produces: không đổi API. Chỉ khẳng định hành vi: `restore()` gọi `_predict_actions`
  nhiều lần cho tới khi một pass không đổi gì (tối đa 3), và pass sau nhìn thấy kết quả
  pass trước.

**Bối cảnh:** Vòng `for iteration in range(3)` là iterative refinement kiểu GECToR —
model được huấn luyện để tag nhiều vòng, pass sau đọc text đã hoa/chấm của pass trước.
Hiện không có comment giải thích và không test nào cover hành vi lặp: mọi test đều
monkeypatch `_predict_actions` bằng `iter([...])` đúng 2 phần tử, tức "2 pass" bị đóng
băng ngầm vào fixture chứ không được khẳng định. Không được xoá vòng lặp.

- [ ] **Step 1: Viết 2 test đỏ cho hành vi lặp**

Thêm vào `tests/test_punctuate.py` sau `test_restore_empty_does_not_load_runtime`:

```python
def test_restore_refines_until_a_pass_changes_nothing(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " hà"), Word(1.0, 2.0, " nội")]
    seen: list[list[str]] = []

    def fake_predict(pieces, runtime, progress_cb=None):
        seen.append([piece.output_core + piece.suffix for piece in pieces])
        if len(seen) == 1:
            return ["$TRANSFORM_CASE_CAPITAL", "$TRANSFORM_CASE_CAPITAL"], 0
        if len(seen) == 2:
            return ["$KEEP", "$APPEND_."], 0
        return ["$KEEP", "$KEEP"], 0

    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(punctuate, "_predict_actions", fake_predict)
    result = punctuate.restore(words)
    assert [word.text for word in result.words] == [" Hà", " Nội."]
    # Pass 2 phải nhìn thấy kết quả pass 1 — đó là lý do vòng lặp tồn tại.
    assert seen == [["hà", "nội"], ["Hà", "Nội"], ["Hà", "Nội."]]


def test_restore_stops_after_first_pass_when_nothing_changes(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên")]
    calls = []

    def fake_predict(pieces, runtime, progress_cb=None):
        calls.append(1)
        return ["$KEEP"], 0

    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(punctuate, "_predict_actions", fake_predict)
    result = punctuate.restore(words)
    assert result.applied is True
    assert len(calls) == 1
```

- [ ] **Step 2: Chạy test**

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: cả hai test PASS ngay (chúng khẳng định hành vi đã đúng). Nếu FAIL,
đó là bug thật trong vòng lặp — báo lại, KHÔNG sửa test cho khớp.

- [ ] **Step 3: Thêm comment giải thích vòng lặp**

Trong `app/punctuate.py`, ngay trước dòng `for iteration in range(3):`, thêm:

```python
        # Iterative refinement kiểu GECToR: model được huấn luyện để tag nhiều vòng,
        # pass sau đọc text đã được hoa/chấm ở pass trước nên bắt thêm được ranh giới
        # câu. Thoát sớm ngay khi một pass không đổi gì, nên chi phí thường là 2 pass
        # chứ không phải 3. progress_cb chỉ gắn vào pass đầu để thanh tiến trình
        # không nhảy lùi.
```

- [ ] **Step 4: Chạy test và lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
```

Expected: PASS, ruff sạch.

- [ ] **Step 5: Commit**

```bash
git add app/punctuate.py tests/test_punctuate.py
git commit -m "test: khang dinh vong lap refinement dau cau" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: Test UI contract parse HTML thay vì so chuỗi

**Files:**

- Test: `tests/test_punctuate.py` (hàm `test_ui_contains_punctuation_checkbox_and_form_contract`, khoảng dòng 432)

**Interfaces:**

- Consumes: `app/static/index.html` (không sửa file này).
- Produces: helper test `_input_attrs(html: str, element_id: str) -> dict[str, str]`.

**Bối cảnh:** Test hiện assert nguyên văn `'type="checkbox" id="punctuate" checked'`.
Đổi thứ tự attribute, thêm `class`, hay format lại HTML là đỏ dù UI vẫn đúng — đó là
test bám vào cách viết chứ không phải hợp đồng. Dùng `html.parser` trong stdlib
(không thêm dependency).

- [ ] **Step 1: Thay test bằng bản parse attribute**

Thay toàn bộ `test_ui_contains_punctuation_checkbox_and_form_contract` trong
`tests/test_punctuate.py` bằng:

```python
def _input_attrs(html: str, element_id: str) -> dict[str, str]:
    from html.parser import HTMLParser

    class Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.found: dict[str, str] | None = None

        def handle_starttag(self, tag, attrs):
            data = {key: (value if value is not None else "") for key, value in attrs}
            if data.get("id") == element_id:
                self.found = data

    parser = Collector()
    parser.feed(html)
    assert parser.found is not None, f"không tìm thấy element id={element_id}"
    return parser.found


def test_ui_contains_punctuation_checkbox_and_form_contract():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    attrs = _input_attrs(html, "punctuate")
    assert attrs["type"] == "checkbox"
    assert "checked" in attrs

    assert "Tự chèn dấu câu (khuyên dùng cho PhoWhisper)" in html
    assert 'fd.append("punctuate"' in html
    assert "punctuateEl.checked" in html
    assert "settings.punctuate" in html
    assert "punctuationMeta.downloaded" in html
```

Đưa `from pathlib import Path` lên block import đầu file (sau `import json`,
trước dòng trống và `import pytest`) và xoá `from pathlib import Path` cục bộ
trong hàm test cũ nếu còn.

- [ ] **Step 2: Chạy test**

```bash
uv run pytest tests/test_punctuate.py::test_ui_contains_punctuation_checkbox_and_form_contract -q
```

Expected: PASS với `app/static/index.html` hiện tại.

- [ ] **Step 3: Chứng minh test vẫn bắt lỗi thật**

Đổi tạm `id="punctuate"` thành `id="punctuate2"` trong `app/static/index.html`, chạy lại
lệnh ở Step 2 và xác nhận FAIL với message `không tìm thấy element id=punctuate`.
Sau đó hoàn nguyên bằng:

```bash
git checkout app/static/index.html
```

- [ ] **Step 4: Chạy test và lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check tests/test_punctuate.py
git status --short app/static/index.html
```

Expected: PASS, ruff sạch, `app/static/index.html` KHÔNG có thay đổi nào.

- [ ] **Step 5: Commit**

```bash
git add tests/test_punctuate.py
git commit -m "test: kiem tra UI dau cau bang parser thay vi so chuoi" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: Eval boundary theo index, bỏ env gate thừa, cập nhật tài liệu

**Files:**

- Modify: `scripts/eval_punctuation.py`
- Modify: `tests/test_punctuate.py` (test mới + sửa `test_real_punctuation_model_contract`)
- Modify: `docs/11-tasks-punctuation-restoration.md:25`
- Modify: `docs/dev/plans/2026-07-19-punctuation-restoration.md` (phụ lục cuối file)

**Interfaces:**

- Consumes: `app.segment.build_sentences(words) -> list[Sentence]` (Sentence có `.start`, `.end`, `.text`).
- Produces: `scripts/eval_punctuation.py` chỉ chạy logic khi `__name__ == "__main__"`;
  các helper `lexical_tokens`, `reference_boundaries`, `sentence_boundaries`, `boundary_f1`
  trở thành import được.

**Bối cảnh 1:** `sentence_boundaries()` map ranh giới câu bằng `word.end in ends`. Hai word
trùng timestamp `end` (rất thường gặp khi ASR trả word rỗng/ngắn) sẽ tạo boundary giả và
làm F1 sai. Phải duyệt tiến theo con trỏ index.

**Bối cảnh 2:** `test_real_punctuation_model_contract` bị gate hai lần: marker `model`
(đã bị `addopts = "-m 'not model'"` loại khỏi suite mặc định) VÀ env `VITRANSCRIPT_MODEL_TEST`.
Gate thứ hai thừa và làm lệnh trong tài liệu dài vô ích.

- [ ] **Step 1: Viết test đỏ cho boundary trùng timestamp**

Thêm vào cuối `tests/test_punctuate.py`:

```python
def _load_eval_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval_punctuation", Path("scripts/eval_punctuation.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sentence_boundaries_ignores_duplicate_end_timestamps():
    module = _load_eval_module()
    words = [
        Word(0.0, 1.0, " a."),
        Word(1.0, 1.0, " b"),
        Word(1.0, 2.0, " c."),
    ]
    # Word 1 trùng end với ranh giới câu đầu nhưng KHÔNG phải ranh giới.
    assert module.sentence_boundaries(words) == {0, 2}
```

- [ ] **Step 2: Chạy test và xác nhận đỏ**

```bash
uv run pytest tests/test_punctuate.py::test_sentence_boundaries_ignores_duplicate_end_timestamps -q
```

Expected: FAIL. Trước khi sửa script, `exec_module` chạy cả phần body và thoát
bằng `SystemExit("Thiếu eval/...")`; sau khi bọc `main()` thì lỗi sẽ là
`assert {0, 1, 2} == {0, 2}`. Cả hai đều là trạng thái đỏ hợp lệ.

- [ ] **Step 3: Sửa `sentence_boundaries` và bọc body vào `main()`**

Trong `scripts/eval_punctuation.py`, thay `sentence_boundaries` bằng:

```python
def sentence_boundaries(words: list[Word]) -> set[int]:
    # Duyệt tiến theo con trỏ: hai word có thể trùng `end`, so timestamp bằng
    # `in` sẽ đánh dấu nhầm word không phải ranh giới câu.
    boundaries: set[int] = set()
    cursor = 0
    for sentence in build_sentences(words):
        while cursor < len(words) and words[cursor].end != sentence.end:
            cursor += 1
        if cursor >= len(words):
            break
        boundaries.add(cursor)
        cursor += 1
    return boundaries
```

Sau đó chuyển toàn bộ phần body top-level (từ `if not WORDS_PATH.exists()` tới hết file)
vào một hàm `main()` và gọi nó dưới guard, giữ nguyên logic và thông điệp:

```python
def main() -> None:
    if not WORDS_PATH.exists() or not REFERENCE_PATH.exists():
        sys.exit("Thiếu eval/punctuation_words.json hoặc punctuation_reference.txt")

    rows = json.loads(WORDS_PATH.read_text(encoding="utf-8"))
    raw = [Word(float(row["start"]), float(row["end"]), str(row["text"])) for row in rows]
    reference = REFERENCE_PATH.read_text(encoding="utf-8").strip()
    if lexical_tokens("".join(word.text for word in raw)) != lexical_tokens(reference):
        sys.exit("Fixture reference phải có cùng lexical words với punctuation_words.json")

    result = punctuate.restore(raw)
    if not result.applied:
        sys.exit(result.warning or "Punctuation không chạy")
    expected = reference_boundaries(reference)
    baseline_f1 = boundary_f1(sentence_boundaries(raw), expected)
    restored_f1 = boundary_f1(sentence_boundaries(result.words), expected)
    baseline_text = " ".join(lexical_tokens("".join(word.text for word in raw)))
    restored_text = " ".join(lexical_tokens("".join(word.text for word in result.words)))
    lexical_wer = wer(baseline_text, restored_text)
    report = {
        "revision": config.PUNCTUATION_MODEL["revision"],
        "baseline_boundary_f1": baseline_f1,
        "restored_boundary_f1": restored_f1,
        "improvement_points": (restored_f1 - baseline_f1) * 100,
        "lexical_wer_vs_baseline": lexical_wer,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["improvement_points"] < 10 or lexical_wer != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Bỏ env gate thừa của model test**

Trong `tests/test_punctuate.py`, sửa `test_real_punctuation_model_contract`: xoá
`import os` cục bộ và hai dòng `if os.environ.get(...) ... pytest.skip(...)`. Giữ nguyên
decorator `@pytest.mark.model` và toàn bộ assertion còn lại.

- [ ] **Step 5: Cập nhật tài liệu**

Trong `docs/11-tasks-punctuation-restoration.md`, sửa dòng evidence bỏ env var:

```markdown
  - `uv run pytest -m model tests/test_punctuate.py::test_real_punctuation_model_contract -v` → PASS (~13s first run)
```

Thêm vào CUỐI `docs/dev/plans/2026-07-19-punctuation-restoration.md`:

```markdown
## Amendments sau review (2026-07-23)

Plan này đã thực thi xong; review hồi cứu tìm ra 5 defect, được sửa theo
`docs/dev/plans/2026-07-23-punctuation-review-fixes.md`. Khi đọc lại plan gốc,
lưu ý các điểm sau đã bị thay thế:

- Task 3 Step 4: `_apply_case` không dùng `str.capitalize()` nữa — nó phá casing giữa từ
  ("iPhone" → "Iphone") mà invariant `casefold()` không bắt được.
- Task 2 Step 3: `_ensure_model_dir()` không return sớm khi cache "đã tải"; nó luôn băm
  lại SHA-256 artifact một lần mỗi process trước khi đưa cho ONNX Runtime.
- Task 4 Step 1: KHÔNG chèn `from app.transcribe import Word` vào giữa file test —
  ruff bật `select = ["E", ...]` nên E402 sẽ đỏ ngay ở step lint của chính task đó.
  Mọi import phải nằm ở block đầu file (đúng như Task 5 Step 1 đã dặn).
- Task 4 Step 4: `_predict_actions` trả `tuple[list[str], int]` (actions, số chunk lỗi);
  một chunk hỏng không được làm mất dấu câu cả file.
- Task 5 Step 1: bỏ env `VITRANSCRIPT_MODEL_TEST` — marker `model` cộng
  `addopts = "-m 'not model'"` đã là gate đủ.
- Task 8 Step 1: test UI parse attribute bằng `html.parser`, không so chuỗi nguyên văn.
```

- [ ] **Step 6: Chạy đầy đủ và lint**

```bash
uv run pytest tests/ -q
uv run ruff check .
```

Expected: toàn bộ suite PASS (1 test `model` deselected), ruff sạch.

- [ ] **Step 7: Commit**

```bash
git add scripts/eval_punctuation.py tests/test_punctuate.py \
  docs/11-tasks-punctuation-restoration.md \
  docs/dev/plans/2026-07-19-punctuation-restoration.md
git commit -m "fix: eval boundary theo index va don gate test model" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Final verification checklist

- [ ] `uv run ruff check .` sạch.
- [ ] `uv run pytest tests/ -v` PASS, không tải model nào.
- [ ] `HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py` vẫn in
      `"Hà Nội là thủ đô Việt Nam. Tôi yêu nó."` — chứng minh 5 fix không đổi hành vi thật.
- [ ] `uv tree | rg -i '(^|[- ])(torch|tensorflow)( |$)'` không có kết quả.
- [ ] `git status --short` không còn file lạ; `app/static/index.html` không bị sửa.
- [ ] PR-13 vẫn BLOCKED (chưa có fixture) — không được đổi thành PASS.
