# Vietnamese Punctuation Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm bước phục hồi dấu câu và viết hoa tiếng Việt bằng ViBERT-CAPU ONNX INT8 sau ASR, trước tách câu, trong khi bảo toàn tuyệt đối số từ và timestamp.

**Architecture:** `app/punctuate.py` sở hữu toàn bộ download, xác minh artifact, tokenization, ONNX inference, lọc action và fallback. Pipeline chỉ nhận `PunctuationResult`, server truyền option/cảnh báo, còn UI cung cấp checkbox mặc định bật. Artifact được pin revision/SHA-256, tải vào data directory và không thực thi code từ model repository.

**Tech Stack:** Python 3.10–3.12, faster-whisper `Word`, ONNX Runtime CPU, Hugging Face Hub, Hugging Face `tokenizers`, NumPy, FastAPI, HTML/JavaScript thuần, pytest, ruff.

---

**Spec:** [../specs/2026-07-19-punctuation-restoration-design.md](../specs/2026-07-19-punctuation-restoration-design.md)

## Preconditions and global constraints

- Chạy mọi lệnh từ `.worktrees/vitranscript-impl/`.
- Worktree đang có thay đổi dở trong `app/segment.py`, `app/static/index.html`,
  `tests/test_core.py` và tài liệu desktop. Không discard, overwrite hoặc stage chúng
  ngoài phần hunk thật sự thuộc punctuation.
- Không thêm dependency kéo theo PyTorch hoặc TensorFlow.
- Không bật `trust_remote_code`; không import Python từ model repository.
- Giữ server ở `127.0.0.1`, một job tại một thời điểm và cache tối đa một ASR model.
- Giữ nguyên URL upstream có typo `speaker-recongition-models`.
- `.bat` không được có dấu tiếng Việt nếu bất kỳ task nào chạm tới file batch.
- Mỗi task theo TDD: test đỏ → implementation tối thiểu → test xanh → ruff → commit.
- Mỗi commit có trailer:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Model smoke có mạng là suite riêng; unit/integration suite không tải weight.
- Không đánh dấu macOS x86_64 hoặc Windows PASS nếu chưa chạy trên máy/VM tương ứng.

## File map

### Create

- `app/punctuate.py` — artifact, runtime, inference, action whitelist, invariant và fallback.
- `tests/test_punctuate.py` — unit/integration contract không tải model.
- `scripts/smoke_punctuation_model.py` — smoke artifact pin và offline-cache.
- `scripts/eval_punctuation.py` — boundary F1 và lexical drift trên fixture riêng.
- `THIRD_PARTY_NOTICES.md` — attribution/license model.
- `docs/11-tasks-punctuation-restoration.md` — tracker PR-01…PR-14 theo nền tảng.

### Modify

- `pyproject.toml` — `onnxruntime`, `tokenizers`, pytest marker `model`.
- `uv.lock` — lock wheel đã resolve.
- `app/config.py` — registry/cache/manifest và setting `punctuate`.
- `app/pipeline.py` — stage punctuation, progress và result metadata.
- `app/server.py` — meta/form/opts/warning/partial recovery.
- `app/static/index.html` — checkbox, helper, settings và FormData.
- `tests/test_core.py` — chỉ cập nhật assertions của pipeline/partial hiện có.
- `README.md` — cách dùng, model download/offline và giới hạn.
- `eval/README.md` — định dạng fixture punctuation riêng tư.
- `.gitignore` — không commit fixture punctuation riêng tư.
- `docs/03-tasks.md` — thêm dòng feature và link tracker sau khi implementation xong.

## Requirement coverage

| Spec ID | Task |
|---|---|
| PR-01, PR-02 | 3–4 |
| PR-03 | 6 |
| PR-04 | 6–8 |
| PR-05 | 4, 6–7 |
| PR-06, PR-07 | 2, 5 |
| PR-08 | 1, 7–8 |
| PR-09 | 7 |
| PR-10 | 1, 9 |
| PR-11 | 9 |
| PR-12 | mọi task; full gate ở Task 9 |
| PR-13 | 9 |
| PR-14 | 5 và tracker Task 9 |

## Task 1: Pinned config, settings, and dependencies

**Files:**

- Create: `tests/test_punctuate.py`
- Modify: `app/config.py:7-117`
- Modify: `pyproject.toml:6-33`
- Modify: `uv.lock`

- [ ] **Step 1: Write failing config/settings tests**

Create `tests/test_punctuate.py` with:

```python
import json


def test_punctuation_model_is_pinned():
    from app.config import PUNCTUATION_MODEL

    assert PUNCTUATION_MODEL == {
        "repo_id": "welcomyou/vibert-capu-onnx",
        "revision": "a7754d037f4a9e29f7f3224f27acb60149eab874",
        "filename": "vibert-capu.int8.onnx",
        "size": 115_707_731,
        "sha256": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
        "license": "CC-BY-SA-4.0",
    }


def test_punctuation_cache_requires_matching_manifest(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = config.punctuation_dir()
    model = root / config.PUNCTUATION_MODEL["filename"]
    model.write_bytes(b"abc")
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", 3)
    assert config.punctuation_is_downloaded() is False

    (root / "manifest.json").write_text(
        json.dumps({
            "revision": config.PUNCTUATION_MODEL["revision"],
            "sha256": config.PUNCTUATION_MODEL["sha256"],
        }),
        encoding="utf-8",
    )
    assert config.punctuation_is_downloaded() is True


def test_punctuate_setting_defaults_true_and_rejects_non_bool(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert config.load_settings()["punctuate"] is True
    assert config.save_settings({"punctuate": False})["punctuate"] is False
    assert config.save_settings({"punctuate": "false"})["punctuate"] is False
```

- [ ] **Step 2: Run the tests and confirm the intended red state**

Run:

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL because `PUNCTUATION_MODEL`, `punctuation_dir()` and the
`punctuate` setting do not exist.

- [ ] **Step 3: Add the config contracts**

Add below `MODEL_REGISTRY` in `app/config.py`:

```python
PUNCTUATION_MODEL = {
    "repo_id": "welcomyou/vibert-capu-onnx",
    "revision": "a7754d037f4a9e29f7f3224f27acb60149eab874",
    "filename": "vibert-capu.int8.onnx",
    "size": 115_707_731,
    "sha256": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
    "license": "CC-BY-SA-4.0",
}
```

Add `"punctuate": True` to `DEFAULT_SETTINGS`. Add these functions after
`models_dir()`:

```python
def punctuation_dir() -> Path:
    d = data_dir() / "punctuation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def punctuation_manifest_path() -> Path:
    return punctuation_dir() / "manifest.json"


def punctuation_is_downloaded() -> bool:
    model_path = punctuation_dir() / PUNCTUATION_MODEL["filename"]
    try:
        manifest = json.loads(punctuation_manifest_path().read_text(encoding="utf-8"))
        return (
            model_path.is_file()
            and model_path.stat().st_size == PUNCTUATION_MODEL["size"]
            and manifest.get("revision") == PUNCTUATION_MODEL["revision"]
            and manifest.get("sha256") == PUNCTUATION_MODEL["sha256"]
        )
    except (OSError, ValueError):
        return False
```

Replace `save_settings()` with a version that only accepts a real boolean for the
new key:

```python
def save_settings(new_values: dict) -> dict:
    s = load_settings()
    updates = {k: v for k, v in new_values.items() if k in DEFAULT_SETTINGS}
    if "punctuate" in updates and not isinstance(updates["punctuate"], bool):
        updates.pop("punctuate")
    s.update(updates)
    _settings_path().write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return s
```

- [ ] **Step 4: Add runtime dependencies and pytest marker**

Add to runtime dependencies in `pyproject.toml`:

```toml
    "onnxruntime>=1.20,<2",
    "tokenizers>=0.20,<1",
```

Add:

```toml
[tool.pytest.ini_options]
markers = [
    "model: downloads/runs pinned model artifacts; excluded from the default suite",
]
addopts = "-m 'not model'"
```

Run:

```bash
uv sync
```

Expected: `uv.lock` updates successfully on the current platform.

- [ ] **Step 5: Verify config tests and the no-PyTorch graph**

Run:

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/config.py tests/test_punctuate.py
if uv tree | rg -i '(^|[- ])(torch|tensorflow)( |$)'; then exit 1; else echo "no torch/tensorflow"; fi
```

Expected: tests PASS, ruff clean, final line `no torch/tensorflow`.

- [ ] **Step 6: Commit Task 1**

```bash
git add pyproject.toml uv.lock app/config.py tests/test_punctuate.py
git commit -m "feat: add pinned punctuation model config" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 2: Verified artifact download and manifest

**Files:**

- Create: `app/punctuate.py`
- Modify: `tests/test_punctuate.py`

- [ ] **Step 1: Add failing artifact tests**

Append:

```python
def test_ensure_model_dir_verifies_hash_and_writes_manifest(monkeypatch, tmp_path):
    from app import config, punctuate

    payload = b"verified-model"
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", len(payload))
    monkeypatch.setitem(
        config.PUNCTUATION_MODEL, "sha256", hashlib.sha256(payload).hexdigest()
    )

    def fake_snapshot_download(**kwargs):
        root = config.punctuation_dir()
        (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(payload)
        (root / "vocab.txt").write_text("[PAD]\n[UNK]\n", encoding="utf-8")
        labels = root / "vocabulary" / "labels.txt"
        labels.parent.mkdir(parents=True)
        labels.write_text("$KEEP\n", encoding="utf-8")
        (root / "config.json").write_text("{}", encoding="utf-8")
        (root / "README.md").write_text("license", encoding="utf-8")
        return str(root)

    monkeypatch.setattr(punctuate, "_snapshot_download", fake_snapshot_download)
    root = punctuate._ensure_model_dir()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == config.PUNCTUATION_MODEL["revision"]
    assert manifest["sha256"] == config.PUNCTUATION_MODEL["sha256"]


def test_ensure_model_dir_rejects_wrong_hash(monkeypatch, tmp_path):
    import pytest

    from app import config, punctuate

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", 3)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "sha256", "0" * 64)

    def fake_snapshot_download(**kwargs):
        root = config.punctuation_dir()
        (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(b"bad")
        return str(root)

    monkeypatch.setattr(punctuate, "_snapshot_download", fake_snapshot_download)
    with pytest.raises(RuntimeError, match="SHA-256"):
        punctuate._ensure_model_dir()
    assert not config.punctuation_manifest_path().exists()
```

Add `import hashlib` beside `import json` in the module import block before running
the tests.

- [ ] **Step 2: Confirm the tests fail because the module is missing**

Run:

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL importing `app.punctuate`.

- [ ] **Step 3: Implement deterministic download and verification**

Create `app/punctuate.py` with this initial content:

```python
"""Phục hồi dấu câu tiếng Việt bằng ViBERT-CAPU ONNX, best-effort."""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import config
from .transcribe import Word

_REQUIRED_FILES = (
    "vibert-capu.int8.onnx",
    "vocab.txt",
    "vocabulary/labels.txt",
    "config.json",
    "README.md",
)


@dataclass
class PunctuationResult:
    words: list[Word]
    applied: bool
    warning: str | None = None


def _snapshot_download(**kwargs):
    from huggingface_hub import snapshot_download

    return snapshot_download(**kwargs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_model_dir() -> Path:
    root = config.punctuation_dir()
    if config.punctuation_is_downloaded():
        return root

    _snapshot_download(
        repo_id=config.PUNCTUATION_MODEL["repo_id"],
        revision=config.PUNCTUATION_MODEL["revision"],
        local_dir=str(root),
        allow_patterns=list(_REQUIRED_FILES),
    )
    model_path = root / config.PUNCTUATION_MODEL["filename"]
    if model_path.stat().st_size != config.PUNCTUATION_MODEL["size"]:
        raise RuntimeError("Model dấu câu sai kích thước")
    actual_hash = _sha256(model_path)
    if actual_hash != config.PUNCTUATION_MODEL["sha256"]:
        raise RuntimeError("Model dấu câu sai SHA-256")
    for relative in _REQUIRED_FILES:
        if not (root / relative).is_file():
            raise RuntimeError(f"Model dấu câu thiếu file runtime: {relative}")

    manifest = {
        "revision": config.PUNCTUATION_MODEL["revision"],
        "sha256": config.PUNCTUATION_MODEL["sha256"],
    }
    tmp = root / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, config.punctuation_manifest_path())
    return root
```

- [ ] **Step 4: Run focused tests and lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
```

Expected: PASS and clean.

- [ ] **Step 5: Commit Task 2**

```bash
git add app/punctuate.py tests/test_punctuate.py
git commit -m "feat: verify punctuation model artifact" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 3: Lazy ONNX runtime and token-action engine

**Files:**

- Modify: `app/punctuate.py`
- Modify: `tests/test_punctuate.py`

- [ ] **Step 1: Add failing runtime/action tests**

Append tests that use no real model:

```python
def test_runtime_is_cached_once(monkeypatch, tmp_path):
    from app import punctuate

    calls = []
    monkeypatch.setattr(punctuate, "_RUNTIME_CACHE", None)
    monkeypatch.setattr(punctuate, "_ensure_model_dir", lambda: tmp_path)
    monkeypatch.setattr(
        punctuate, "_create_runtime", lambda root: calls.append(root) or object()
    )
    assert punctuate._load_runtime() is punctuate._load_runtime()
    assert calls == [tmp_path]


def test_case_actions_are_exact_and_unsupported_actions_keep_text():
    from app.punctuate import _apply_case

    assert _apply_case("hà", "$TRANSFORM_CASE_CAPITAL") == "Hà"
    assert _apply_case("who", "$TRANSFORM_CASE_UPPER") == "WHO"
    assert _apply_case("VN", "$TRANSFORM_CASE_LOWER") == "vn"
    assert _apply_case("iphone", "$TRANSFORM_CASE_CAPITAL_1") == "iPhone"
    assert _apply_case("iphone", "$TRANSFORM_CASE_UPPER_-1") == "IPHONe"
    assert _apply_case("nguyên", "$TRANSFORM_VERB_VB_VBN") == "nguyên"
    assert _apply_case("nguyên", "$MERGE_SPACE") == "nguyên"


def test_chunk_ranges_have_48_words_and_12_overlap():
    from app.punctuate import _chunk_ranges

    assert _chunk_ranges(100) == [(0, 48), (36, 84), (72, 100)]
    assert _chunk_ranges(2) == [(0, 2)]
```

- [ ] **Step 2: Run red tests**

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL for missing `_load_runtime`, `_apply_case`, `_chunk_ranges`.

- [ ] **Step 3: Add lazy runtime and strict label contract**

Append to `app/punctuate.py`:

```python
@dataclass
class _Runtime:
    session: object
    tokenizer: object
    labels: list[str]


_EXPECTED_LABELS = [
    "$KEEP",
    "$TRANSFORM_CASE_CAPITAL",
    "$APPEND_,",
    "$APPEND_.",
    "$TRANSFORM_VERB_VB_VBN",
    "$TRANSFORM_CASE_UPPER",
    "$APPEND_:",
    "$APPEND_?",
    "$TRANSFORM_VERB_VB_VBC",
    "$TRANSFORM_CASE_LOWER",
    "$TRANSFORM_CASE_CAPITAL_1",
    "$TRANSFORM_CASE_UPPER_-1",
    "$MERGE_SPACE",
    "@@UNKNOWN@@",
    "@@PADDING@@",
]
_RUNTIME_CACHE: _Runtime | None = None


def _create_runtime(root: Path) -> _Runtime:
    import onnxruntime as ort
    from tokenizers import BertWordPieceTokenizer

    labels = (root / "vocabulary" / "labels.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    if labels != _EXPECTED_LABELS:
        raise RuntimeError("Label contract của model dấu câu không khớp")
    tokenizer = BertWordPieceTokenizer(str(root / "vocab.txt"), lowercase=False)
    session = ort.InferenceSession(
        str(root / config.PUNCTUATION_MODEL["filename"]),
        providers=["CPUExecutionProvider"],
    )
    input_names = {item.name for item in session.get_inputs()}
    output_names = {item.name for item in session.get_outputs()}
    if input_names != {"input_ids", "attention_mask", "token_type_ids", "input_offsets"}:
        raise RuntimeError("Input contract của model dấu câu không khớp")
    if not {"logits", "detect_logits"}.issubset(output_names):
        raise RuntimeError("Output contract của model dấu câu không khớp")
    return _Runtime(session=session, tokenizer=tokenizer, labels=labels)


def _load_runtime() -> _Runtime:
    global _RUNTIME_CACHE
    if _RUNTIME_CACHE is None:
        _RUNTIME_CACHE = _create_runtime(_ensure_model_dir())
    return _RUNTIME_CACHE
```

- [ ] **Step 4: Add pure case and chunk helpers**

Append:

```python
_CASE_ACTIONS = {
    "$TRANSFORM_CASE_CAPITAL",
    "$TRANSFORM_CASE_UPPER",
    "$TRANSFORM_CASE_LOWER",
    "$TRANSFORM_CASE_CAPITAL_1",
    "$TRANSFORM_CASE_UPPER_-1",
}
_APPEND_ACTIONS = {
    "$APPEND_,": ",",
    "$APPEND_.": ".",
    "$APPEND_:": ":",
    "$APPEND_?": "?",
}


def _apply_case(token: str, action: str) -> str:
    if action == "$TRANSFORM_CASE_LOWER":
        return token.lower()
    if action == "$TRANSFORM_CASE_UPPER":
        return token.upper()
    if action == "$TRANSFORM_CASE_CAPITAL":
        return token.capitalize()
    if action == "$TRANSFORM_CASE_CAPITAL_1" and len(token) > 1:
        return token[0] + token[1:].capitalize()
    if action == "$TRANSFORM_CASE_UPPER_-1" and token:
        return token[:-1].upper() + token[-1]
    return token


def _chunk_ranges(count: int) -> list[tuple[int, int]]:
    if count <= 0:
        return []
    ranges = []
    for start in range(0, count, 36):
        end = min(start + 48, count)
        ranges.append((start, end))
        if end == count:
            break
    return ranges
```

- [ ] **Step 5: Run focused verification and commit**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
git add app/punctuate.py tests/test_punctuate.py
git commit -m "feat: load punctuation runtime lazily" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: tests PASS, ruff clean, one task-scoped commit.

## Task 4: Word-safe inference, overlap merge, invariants, and fallback

**Files:**

- Modify: `app/punctuate.py`
- Modify: `tests/test_punctuate.py`

- [ ] **Step 1: Add failing behavior tests**

Append:

```python
from app.transcribe import Word


def _word_tuples(words):
    return [(w.start, w.end, w.text) for w in words]


def test_restore_keeps_count_timestamps_input_and_blocks_word_edits(monkeypatch):
    from app import punctuate

    original = [Word(0.0, 0.5, " xin"), Word(0.5, 1.0, " chào")]
    before = _word_tuples(original)
    calls = iter([
        ["$TRANSFORM_CASE_CAPITAL", "$APPEND_."],
        ["$KEEP", "$KEEP"],
    ])
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate, "_predict_actions", lambda pieces, runtime, progress_cb=None: next(calls)
    )
    result = punctuate.restore(original)
    assert result.applied is True and result.warning is None
    assert _word_tuples(result.words) == [(0.0, 0.5, " Xin"), (0.5, 1.0, " chào.")]
    assert _word_tuples(original) == before


def test_restore_preserves_existing_punctuation_and_multi_token_word(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 2.0, " hà nội, việt nam")]
    calls = iter([
        ["$TRANSFORM_CASE_CAPITAL", "$APPEND_.", "$TRANSFORM_CASE_CAPITAL", "$KEEP"],
        ["$KEEP", "$KEEP", "$KEEP", "$KEEP"],
    ])
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate, "_predict_actions", lambda pieces, runtime, progress_cb=None: next(calls)
    )
    result = punctuate.restore(words)
    assert _word_tuples(result.words) == [(0.0, 2.0, " Hà nội, Việt nam")]


def test_restore_falls_back_whole_input_on_any_error(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên bản")]
    monkeypatch.setattr(
        punctuate, "_load_runtime", lambda: (_ for _ in ()).throw(RuntimeError("secret path"))
    )
    result = punctuate.restore(words)
    assert result.applied is False
    assert _word_tuples(result.words) == _word_tuples(words)
    assert result.warning == (
        "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."
    )
    assert "secret" not in result.warning


def test_restore_falls_back_when_final_invariant_breaks(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên")]
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate,
        "_predict_actions",
        lambda pieces, runtime, progress_cb=None: ["$KEEP"],
    )
    monkeypatch.setattr(
        punctuate,
        "_rebuild_words",
        lambda words, layouts, pieces: [Word(0.0, 1.0, " từ-khác")],
    )
    result = punctuate.restore(words)
    assert result.applied is False
    assert _word_tuples(result.words) == _word_tuples(words)


def test_restore_empty_does_not_load_runtime(monkeypatch):
    from app import punctuate

    monkeypatch.setattr(
        punctuate, "_load_runtime", lambda: (_ for _ in ()).throw(AssertionError())
    )
    result = punctuate.restore([])
    assert result == punctuate.PunctuationResult([], False, None)


def test_overlap_prefers_prediction_furthest_from_chunk_edge():
    from app.punctuate import _choose_overlapping

    chosen = _choose_overlapping(60, [
        (0, 48, ["$KEEP"] * 48),
        (36, 60, ["$APPEND_."] * 24),
    ])
    assert chosen[36] == "$KEEP"
    assert chosen[47] == "$APPEND_."


def test_predict_actions_builds_word_offsets_for_onnx():
    import numpy as np

    from app import punctuate

    class Encoding:
        ids = [101, 11, 12, 102]
        attention_mask = [1, 1, 1, 1]
        type_ids = [0, 0, 0, 0]
        word_ids = [None, 0, 1, None]

    class Tokenizer:
        def encode(self, tokens, is_pretokenized):
            assert tokens == ["xin", "chào"]
            assert is_pretokenized is True
            return Encoding()

    class Session:
        def __init__(self):
            self.feeds = None

        def run(self, outputs, feeds):
            self.feeds = feeds
            logits = np.zeros((1, 2, 15), dtype=np.float32)
            logits[0, 0, 3] = 10.0
            logits[0, 1, 0] = 10.0
            return [logits, np.zeros((1, 2, 4), dtype=np.float32)]

    _, pieces = punctuate._parse_words([
        Word(0.0, 0.5, " xin"), Word(0.5, 1.0, " chào")
    ])
    session = Session()
    runtime = punctuate._Runtime(session, Tokenizer(), punctuate._EXPECTED_LABELS)
    assert punctuate._predict_actions(pieces, runtime) == ["$APPEND_.", "$KEEP"]
    assert session.feeds["input_offsets"].tolist() == [[1, 2]]
```

- [ ] **Step 2: Confirm red failures**

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL for missing `restore`, `_predict_actions`, `_choose_overlapping`.

- [ ] **Step 3: Implement parsing and safe reconstruction**

Add `import logging`, `import re`, and `import numpy as np`. Add:

```python
log = logging.getLogger("vitranscript")
_TARGET_PUNCTUATION = ".,:?"
_SPAN_RE = re.compile(r"\s+|[^\s]+")
_WARNING = "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."


@dataclass
class _Piece:
    word_index: int
    span_index: int
    model_core: str
    output_core: str
    suffix: str


def _parse_words(words: list[Word]) -> tuple[list[list[str]], list[_Piece]]:
    layouts: list[list[str]] = []
    pieces: list[_Piece] = []
    for word_index, word in enumerate(words):
        spans = _SPAN_RE.findall(word.text)
        layouts.append(spans)
        for span_index, span in enumerate(spans):
            if span.isspace():
                continue
            core = span.rstrip(_TARGET_PUNCTUATION)
            suffix = span[len(core):]
            if not core:
                continue
            pieces.append(_Piece(
                word_index=word_index,
                span_index=span_index,
                model_core=core.lower(),
                output_core=core,
                suffix=suffix,
            ))
    return layouts, pieces


def _apply_safe_action(piece: _Piece, action: str) -> bool:
    before = (piece.model_core, piece.output_core, piece.suffix)
    if action in _CASE_ACTIONS:
        piece.model_core = _apply_case(piece.model_core, action)
        piece.output_core = _apply_case(piece.output_core, action)
    elif action in _APPEND_ACTIONS and not piece.suffix:
        piece.suffix = _APPEND_ACTIONS[action]
    return before != (piece.model_core, piece.output_core, piece.suffix)


def _rebuild_words(words: list[Word], layouts: list[list[str]], pieces: list[_Piece]) -> list[Word]:
    rebuilt = [list(spans) for spans in layouts]
    for piece in pieces:
        rebuilt[piece.word_index][piece.span_index] = piece.output_core + piece.suffix
    return [
        Word(word.start, word.end, "".join(rebuilt[index]))
        for index, word in enumerate(words)
    ]


def _signature(text: str) -> str:
    return text.translate(str.maketrans("", "", _TARGET_PUNCTUATION)).casefold()


def _invariants_hold(original: list[Word], restored: list[Word]) -> bool:
    return len(original) == len(restored) and all(
        before.start == after.start
        and before.end == after.end
        and _signature(before.text) == _signature(after.text)
        for before, after in zip(original, restored)
    )
```

- [ ] **Step 4: Implement ONNX prediction and deterministic overlap**

Add:

```python
def _encode_chunk(runtime: _Runtime, pieces: list[_Piece]):
    tokens: list[str] = []
    lexical_positions: list[int] = []
    for piece in pieces:
        lexical_positions.append(len(tokens))
        tokens.append(piece.model_core)
        tokens.extend(piece.suffix)
    encoding = runtime.tokenizer.encode(tokens, is_pretokenized=True)
    first_subword: dict[int, int] = {}
    for index, word_id in enumerate(encoding.word_ids):
        if word_id is not None and word_id not in first_subword:
            first_subword[word_id] = index
    offsets = [first_subword[position] for position in lexical_positions]
    return {
        "input_ids": np.asarray([encoding.ids], dtype=np.int64),
        "attention_mask": np.asarray([encoding.attention_mask], dtype=np.int64),
        "token_type_ids": np.asarray([encoding.type_ids], dtype=np.int64),
        "input_offsets": np.asarray([offsets], dtype=np.int64),
    }


def _choose_overlapping(
    count: int,
    predictions: list[tuple[int, int, list[str]]],
) -> list[str]:
    selected = ["$KEEP"] * count
    margins = [-1] * count
    starts = [count] * count
    for start, end, actions in predictions:
        for local_index, action in enumerate(actions):
            global_index = start + local_index
            margin = min(local_index, end - start - local_index - 1)
            if margin > margins[global_index] or (
                margin == margins[global_index] and start < starts[global_index]
            ):
                selected[global_index] = action
                margins[global_index] = margin
                starts[global_index] = start
    return selected


def _predict_actions(
    pieces: list[_Piece],
    runtime: _Runtime,
    progress_cb: Callable[[float], None] | None = None,
) -> list[str]:
    predictions = []
    furthest = 0
    for start, end in _chunk_ranges(len(pieces)):
        feeds = _encode_chunk(runtime, pieces[start:end])
        logits = runtime.session.run(["logits", "detect_logits"], feeds)[0]
        label_ids = np.argmax(logits[0], axis=-1).tolist()
        actions = [runtime.labels[index] for index in label_ids]
        if len(actions) != end - start:
            raise RuntimeError("Model dấu câu trả sai số word")
        predictions.append((start, end, actions))
        furthest = max(furthest, end)
        if progress_cb:
            progress_cb(furthest / len(pieces))
    return _choose_overlapping(len(pieces), predictions)
```

- [ ] **Step 5: Implement public restore with whole-input fallback**

Add:

```python
def restore(
    words: list[Word],
    *,
    progress_cb: Callable[[float], None] | None = None,
) -> PunctuationResult:
    original = [Word(word.start, word.end, word.text) for word in words]
    if not original:
        return PunctuationResult([], False, None)
    try:
        layouts, pieces = _parse_words(original)
        if not pieces:
            return PunctuationResult(original, True, None)
        runtime = _load_runtime()
        last_progress = 0.0

        def monotonic(value: float) -> None:
            nonlocal last_progress
            last_progress = max(last_progress, min(value * 0.9, 0.9))
            if progress_cb:
                progress_cb(last_progress)

        for iteration in range(3):
            actions = _predict_actions(
                pieces, runtime, monotonic if iteration == 0 else None
            )
            changed = False
            for piece, action in zip(pieces, actions):
                changed = _apply_safe_action(piece, action) or changed
            if not changed:
                break
        restored = _rebuild_words(original, layouts, pieces)
        if not _invariants_hold(original, restored):
            raise RuntimeError("Invariant punctuation bị vi phạm")
        if progress_cb:
            progress_cb(1.0)
        return PunctuationResult(restored, True, None)
    except Exception:
        log.exception("Không thể phục hồi dấu câu")
        return PunctuationResult(original, False, _WARNING)
```

- [ ] **Step 6: Run unit suite and lint**

```bash
uv run pytest tests/test_punctuate.py -q
uv run ruff check app/punctuate.py tests/test_punctuate.py
```

Expected: all punctuation unit tests PASS, ruff clean. If the overlap assertion does
not match the documented “furthest edge” rule, fix the test/data, not the rule.

- [ ] **Step 7: Commit Task 4**

```bash
git add app/punctuate.py tests/test_punctuate.py
git commit -m "feat: restore punctuation without changing words" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 5: Real pinned-model contract smoke

**Files:**

- Create: `scripts/smoke_punctuation_model.py`
- Modify: `tests/test_punctuate.py`

- [ ] **Step 1: Add an opt-in pytest smoke**

Append:

```python
@pytest.mark.model
def test_real_punctuation_model_contract():
    import os

    if os.environ.get("VITRANSCRIPT_MODEL_TEST") != "1":
        pytest.skip("set VITRANSCRIPT_MODEL_TEST=1 to run the pinned artifact")
    from app import config, punctuate

    words = [
        Word(float(i), float(i + 1), " " + token)
        for i, token in enumerate("hà nội là thủ đô việt nam tôi yêu nó".split())
    ]
    result = punctuate.restore(words)
    text = "".join(word.text for word in result.words).strip()
    assert result.applied is True, result.warning
    assert config.punctuation_is_downloaded() is True
    assert any(mark in text for mark in ".,:?")
    assert any(char.isupper() for char in text)
    assert punctuate._invariants_hold(words, result.words)
```

Add `import pytest` to the module import block before this test; do not place the
import between existing test functions.

- [ ] **Step 2: Add a command-line smoke wrapper**

Create `scripts/smoke_punctuation_model.py`:

```python
"""Smoke ViBERT-CAPU ONNX đã pin; lần đầu cần mạng."""

import json

from app import config, punctuate
from app.transcribe import Word

tokens = "hà nội là thủ đô việt nam tôi yêu nó".split()
words = [Word(float(i), float(i + 1), " " + token) for i, token in enumerate(tokens)]
result = punctuate.restore(words)
text = "".join(word.text for word in result.words).strip()
assert result.applied, result.warning
assert config.punctuation_is_downloaded()
assert any(mark in text for mark in ".,:?")
assert any(char.isupper() for char in text)
assert punctuate._invariants_hold(words, result.words)
print(json.dumps({
    "revision": config.PUNCTUATION_MODEL["revision"],
    "sha256": config.PUNCTUATION_MODEL["sha256"],
    "text": text,
}, ensure_ascii=False, indent=2))
```

- [ ] **Step 3: Run online smoke, then offline smoke**

Run:

```bash
VITRANSCRIPT_MODEL_TEST=1 uv run pytest -m model \
  tests/test_punctuate.py::test_real_punctuation_model_contract -v
HF_HUB_OFFLINE=1 uv run python scripts/smoke_punctuation_model.py
```

Expected: both commands exit 0; second command performs no network download. Record
platform, elapsed time and peak RSS in `docs/11-tasks-punctuation-restoration.md`.

If the pinned artifact fails its published input/output contract, stop here. Do not
wire a model that only passes fake tests; record the exact shape/tokenizer failure
in the tracker and return to spec review.

- [ ] **Step 4: Commit Task 5**

```bash
git add scripts/smoke_punctuation_model.py tests/test_punctuate.py
git commit -m "test: smoke pinned punctuation model" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Task 6: Pipeline stage, progress, and result metadata

**Files:**

- Modify: `app/pipeline.py:1-88`
- Modify: `tests/test_punctuate.py`
- Modify: `tests/test_core.py` pipeline assertions only

- [ ] **Step 1: Add failing pipeline tests**

Append:

```python
def test_pipeline_punctuates_before_sentence_split(monkeypatch, tmp_path):
    from app import config, media, pipeline, punctuate, transcribe

    monkeypatch.setattr(media, "to_wav16k", lambda source, out: out)
    monkeypatch.setattr(media, "wav_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: True)
    monkeypatch.setattr(config, "punctuation_is_downloaded", lambda: True)
    monkeypatch.setattr(config, "load_settings", lambda: {"beam_size": 5})
    monkeypatch.setattr(transcribe, "load_model", lambda key: object())
    monkeypatch.setattr(
        transcribe,
        "transcribe",
        lambda *args, **kwargs: [
            Word(0.0, 1.0, " xin"),
            Word(1.0, 2.0, " chào"),
            Word(2.0, 3.0, " bạn"),
        ],
    )
    monkeypatch.setattr(
        punctuate,
        "restore",
        lambda words, progress_cb=None: punctuate.PunctuationResult(
            [Word(0.0, 1.0, " Xin."), Word(1.0, 2.0, " chào"), Word(2.0, 3.0, " bạn.")],
            True,
            None,
        ),
    )
    result = pipeline.run(
        tmp_path / "in.wav", tmp_path, "phowhisper-small",
        enable_diarization=False, enable_punctuation=True,
    )
    assert [row["text"] for row in result["sentences"]] == ["Xin.", "chào bạn."]
    assert result["punctuation"]["applied"] is True


def test_pipeline_disabled_does_not_call_punctuation(monkeypatch, tmp_path):
    from app import config, media, pipeline, punctuate, transcribe

    monkeypatch.setattr(media, "to_wav16k", lambda source, out: out)
    monkeypatch.setattr(media, "wav_duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: True)
    monkeypatch.setattr(config, "load_settings", lambda: {"beam_size": 5})
    monkeypatch.setattr(transcribe, "load_model", lambda key: object())
    monkeypatch.setattr(
        transcribe, "transcribe", lambda *args, **kwargs: [Word(0.0, 1.0, " nguyên")]
    )
    monkeypatch.setattr(
        punctuate, "restore", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError())
    )
    result = pipeline.run(
        tmp_path / "in.wav", tmp_path, "phowhisper-small",
        enable_diarization=False, enable_punctuation=False,
    )
    assert result["punctuation"] == {
        "requested": False,
        "applied": False,
        "backend": "vibert-capu-onnx-int8",
        "warning": None,
    }
```

- [ ] **Step 2: Run red pipeline tests**

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL because `pipeline.run()` has no `enable_punctuation` argument/result.

- [ ] **Step 3: Wire the stage into `pipeline.py`**

Add `punctuate` to the relative imports. Add this parameter after `language`:

```python
enable_punctuation: bool = True,
```

Change transcription progress from `12 + f * 58` to `12 + f * 54`. Immediately
after transcription add:

```python
punctuation_meta = {
    "requested": enable_punctuation,
    "applied": False,
    "backend": "vibert-capu-onnx-int8",
    "warning": None,
}
if enable_punctuation:
    downloaded = config.punctuation_is_downloaded()
    report(
        "punctuate",
        66,
        "Đang phục hồi dấu câu…" if downloaded
        else "Lần đầu dùng dấu câu: đang tải model (~110 MB)…",
    )
    restored = punctuate.restore(
        words,
        progress_cb=lambda f: report(
            "punctuate", 66 + f * 6, f"Đang phục hồi dấu câu… {int(f * 100)}%"
        ),
    )
    words = restored.words
    punctuation_meta["applied"] = restored.applied
    punctuation_meta["warning"] = restored.warning
```

Keep diarization at `72 + f * 20`, finalize at 94. Add to the returned dict:

```python
"punctuation": punctuation_meta,
```

- [ ] **Step 4: Update existing pipeline test expectations**

In `test_pipeline_writes_partial_checkpoint`, call `pipeline.run(...,
enable_punctuation=False)` so the old checkpoint test remains isolated from the new
optional stage. Do not alter its existing checkpoint assertions.

- [ ] **Step 5: Verify and commit Task 6**

```bash
uv run pytest tests/test_punctuate.py tests/test_core.py -q
uv run ruff check app/pipeline.py tests/test_punctuate.py tests/test_core.py
git add app/pipeline.py tests/test_punctuate.py tests/test_core.py
git commit -m "feat: add punctuation pipeline stage" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: focused suite PASS and no unrelated hunks staged from the pre-existing
`tests/test_core.py` edits.

## Task 7: Server API, warning composition, and partial recovery

**Files:**

- Modify: `app/server.py:115-288`
- Modify: `tests/test_punctuate.py`
- Modify: `tests/test_core.py` partial recovery assertion only

- [ ] **Step 1: Add failing meta/API tests**

Append:

```python
def test_meta_exposes_punctuation_model(monkeypatch):
    from fastapi.testclient import TestClient
    from app import config, server

    monkeypatch.setattr(config, "punctuation_is_downloaded", lambda: True)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: False)
    monkeypatch.setattr(config, "load_settings", lambda: {"punctuate": True})
    monkeypatch.setattr(config, "load_glossary_text", lambda: "")
    payload = TestClient(server.app).get("/api/meta").json()["punctuation"]
    assert payload == {"downloaded": True, "size": "~110 MB", "license": "CC-BY-SA-4.0"}


def test_create_job_passes_and_persists_punctuate(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import config, media, server

    captured = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            captured["opts"] = args[2]

        def start(self):
            return None

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(media, "duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)
    server.JOBS.clear()
    try:
        response = TestClient(server.app).post(
            "/api/jobs",
            files={"file": ("hop.wav", b"RIFF", "audio/wav")},
            data={"model": "phowhisper-small", "punctuate": "false"},
        )
        assert response.status_code == 200
        assert captured["opts"]["punctuate"] is False
        assert config.load_settings()["punctuate"] is False

        server.JOBS.clear()
        response = TestClient(server.app).post(
            "/api/jobs",
            files={"file": ("hop.wav", b"RIFF", "audio/wav")},
            data={"model": "phowhisper-small"},
        )
        assert response.status_code == 200
        assert captured["opts"]["punctuate"] is True
    finally:
        server.JOBS.clear()


def test_run_job_appends_punctuation_warning_to_existing_note(monkeypatch, tmp_path):
    from app import pipeline, server

    job_id = "punctwarn001"
    server.JOBS[job_id] = {"status": "running", "note": "Đã tắt diarization."}
    monkeypatch.setattr(server, "_save_job", lambda *args: None)
    monkeypatch.setattr(
        pipeline,
        "run",
        lambda *args, **kwargs: {
            "sentences": [], "duration": 1.0, "punctuation": {
                "warning": (
                    "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."
                )
            },
        },
    )
    server._run_job(job_id, tmp_path / "in.wav", {
        "model": "phowhisper-small", "language": "vi", "diarize": False,
        "punctuate": True, "num_speakers": 0, "glossary": "",
    })
    assert server.JOBS[job_id]["status"] == "done"
    assert server.JOBS[job_id]["note"].splitlines() == [
        "Đã tắt diarization.",
        "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên.",
    ]
    server.JOBS.pop(job_id, None)
```

- [ ] **Step 2: Run red server tests**

```bash
uv run pytest tests/test_punctuate.py -q
```

Expected: FAIL because meta/form/opts/warning are absent.

- [ ] **Step 3: Implement meta, form, settings, and opts**

Add to `meta()`:

```python
"punctuation": {
    "downloaded": config.punctuation_is_downloaded(),
    "size": "~110 MB",
    "license": config.PUNCTUATION_MODEL["license"],
},
```

Add form parameter:

```python
punctuate: Annotated[bool, Form()] = True,
```

Store `"punctuate": punctuate` in the initial job dict, pass it to
`config.save_settings()`, add it to `opts`, and pass this argument in `_run_job()`:

```python
enable_punctuation=opts["punctuate"],
```

- [ ] **Step 4: Compose warnings without overwriting long-audio notes**

After `pipeline.run()` and before `job.update(...)`, add:

```python
warning = (result.get("punctuation") or {}).get("warning")
if warning:
    existing = str(job.get("note") or "").strip()
    job["note"] = "\n".join(part for part in (existing, warning) if part)
```

Keep this code inside `_JOBS_LOCK` so note/result/status are saved atomically in the
same snapshot.

- [ ] **Step 5: Mark recovered partials as unpunctuated**

In the partial `result` dict add:

```python
"punctuation": {
    "requested": bool(disk.get("punctuate", True)),
    "applied": False,
    "backend": "vibert-capu-onnx-int8",
    "warning": "Bản khôi phục chưa được phục hồi dấu câu.",
},
```

Append the same sentence to `disk["note"]` without overwriting an existing note. In
`test_get_job_recovers_partial_from_disk`, assert `applied is False` and that note
contains `chưa được phục hồi dấu câu`.

- [ ] **Step 6: Verify and commit Task 7**

```bash
uv run pytest tests/test_punctuate.py tests/test_core.py -q
uv run ruff check app/server.py tests/test_punctuate.py tests/test_core.py
git add app/server.py tests/test_punctuate.py tests/test_core.py
git commit -m "feat: expose punctuation job option" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: API/default/fallback/partial tests PASS. Inspect staged diff to ensure the
unrelated speaker-select changes in `tests/test_core.py` remain unstaged.

## Task 8: UI checkbox and persisted model status

**Files:**

- Modify: `app/static/index.html:279-310,360-500,660-678`
- Modify: `tests/test_punctuate.py`

- [ ] **Step 1: Add a failing static UI contract test**

Append:

```python
def test_ui_contains_punctuation_checkbox_and_form_contract():
    from pathlib import Path

    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'type="checkbox" id="punctuate" checked' in html
    assert "Tự chèn dấu câu (khuyên dùng cho PhoWhisper)" in html
    assert 'fd.append("punctuate", punctuateEl.checked ? "true" : "false")' in html
    assert "settings.punctuate" in html
    assert "data.punctuation.downloaded" in html
```

- [ ] **Step 2: Run red UI test**

```bash
uv run pytest tests/test_punctuate.py::test_ui_contains_punctuation_checkbox_and_form_contract -q
```

Expected: FAIL because markup/JavaScript is missing.

- [ ] **Step 3: Add checkbox and helper text**

Immediately before the diarization field add:

```html
<div class="field">
  <label class="check">
    <input type="checkbox" id="punctuate" checked />
    Tự chèn dấu câu (khuyên dùng cho PhoWhisper)
  </label>
  <div class="hint" id="punctuationHint">Lần đầu tải model dấu câu ~110 MB.</div>
</div>
```

Do not replace the existing `.spk-select` CSS or sentence-threshold edits already in
the dirty worktree.

- [ ] **Step 4: Wire settings/meta and FormData**

Add DOM bindings:

```javascript
const punctuateEl = $("punctuate");
const punctuationHintEl = $("punctuationHint");
```

In `loadMeta()` after applying language:

```javascript
if (typeof settings.punctuate === "boolean") punctuateEl.checked = settings.punctuate;
const punctuationMeta = data.punctuation || {};
punctuationHintEl.textContent = punctuationMeta.downloaded
  ? "Model dấu câu đã tải · chạy offline được."
  : "Lần đầu tải model dấu câu ~110 MB; các lần sau chạy offline.";
```

In the submit handler after `language`:

```javascript
fd.append("punctuate", punctuateEl.checked ? "true" : "false");
```

- [ ] **Step 5: Verify static contract and run the existing UI manually**

```bash
uv run pytest tests/test_punctuate.py::test_ui_contains_punctuation_checkbox_and_form_contract -q
uv run ruff check tests/test_punctuate.py
uv run python -m app.server
```

Expected manual checks:

- checkbox visible and readable at 100% and 125% browser zoom;
- helper changes between “lần đầu tải” and “đã tải” according to meta;
- reload restores saved choice;
- existing speaker dropdown remains wide/readable;
- server still binds only `127.0.0.1`.

Stop the server with Ctrl+C after the check.

- [ ] **Step 6: Commit Task 8**

```bash
git add -p app/static/index.html
git add tests/test_punctuate.py
git diff --cached --check
git commit -m "feat: add punctuation UI option" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Stage only punctuation hunks; preserve pre-existing `.spk-select` changes for their
own commit.

## Task 9: Evaluation, notices, tracker, and release verification

**Files:**

- Create: `scripts/eval_punctuation.py`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `docs/11-tasks-punctuation-restoration.md`
- Modify: `eval/README.md`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/03-tasks.md`

- [ ] **Step 1: Add the boundary evaluator**

Create `scripts/eval_punctuation.py`:

```python
"""Đo boundary F1 của punctuation trên fixture word-aligned riêng tư."""

import json
import sys
from pathlib import Path

from jiwer import wer

from app import config, punctuate
from app.segment import build_sentences
from app.transcribe import Word

ROOT = Path(__file__).parent.parent
WORDS_PATH = ROOT / "eval" / "punctuation_words.json"
REFERENCE_PATH = ROOT / "eval" / "punctuation_reference.txt"
PUNCTUATION = ".,:?"


def lexical_tokens(text: str) -> list[str]:
    table = str.maketrans("", "", PUNCTUATION)
    normalized = [token.translate(table).casefold() for token in text.split()]
    return [token for token in normalized if token]


def reference_boundaries(text: str) -> set[int]:
    boundaries = set()
    index = -1
    for token in text.split():
        index += 1
        if token.rstrip().endswith((".", "?")):
            boundaries.add(index)
    return boundaries


def sentence_boundaries(words: list[Word]) -> set[int]:
    ends = {sentence.end for sentence in build_sentences(words)}
    return {index for index, word in enumerate(words) if word.end in ends}


def boundary_f1(predicted: set[int], expected: set[int], tolerance: int = 2) -> float:
    pred = sorted(predicted)
    gold = sorted(expected)
    matches = [[0] * (len(gold) + 1) for _ in range(len(pred) + 1)]
    for i, prediction in enumerate(pred, start=1):
        for j, reference in enumerate(gold, start=1):
            matches[i][j] = max(matches[i - 1][j], matches[i][j - 1])
            if abs(prediction - reference) <= tolerance:
                matches[i][j] = max(matches[i][j], matches[i - 1][j - 1] + 1)
    true_positive = matches[-1][-1]
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


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
```

- [ ] **Step 2: Document private fixture format**

Append to `eval/README.md`:

```markdown
## Đánh giá phục hồi dấu câu

Tạo `punctuation_words.json` từ 3–5 phút ASR thô dưới dạng list object
`{"start": 0.0, "end": 0.5, "text": " xin"}`. Tạo
`punctuation_reference.txt` bằng đúng các lexical word đó, chỉ thêm viết hoa và dấu
`. , : ?`. Hai file chứa dữ liệu riêng tư, không commit.

Chạy `uv run python scripts/eval_punctuation.py`. Gate đạt khi boundary F1 tăng ít
nhất 10 điểm phần trăm và lexical WER so với ASR thô bằng 0.
```

Ensure `.gitignore` contains exact entries:

```gitignore
eval/punctuation_words.json
eval/punctuation_reference.txt
```

- [ ] **Step 3: Add third-party notice**

Create `THIRD_PARTY_NOTICES.md`:

```markdown
# Third-party notices

## ViBERT-CAPU ONNX INT8

- Runtime artifact: `welcomyou/vibert-capu-onnx`
- Revision: `a7754d037f4a9e29f7f3224f27acb60149eab874`
- Source: https://huggingface.co/welcomyou/vibert-capu-onnx
- Original model: `dragonSwing/vibert-capu`
- Original source: https://huggingface.co/dragonSwing/vibert-capu
- License stated by the model repositories: CC-BY-SA-4.0

ViTranscript downloads this model on first use. Model weights are not stored in this
source repository or bundled in the installer. See the linked model cards for the
complete attribution and license terms.
```

- [ ] **Step 4: Update user README**

Add after “File dài (1–4 giờ)”:

```markdown
## Phục hồi dấu câu

Tùy chọn **Tự chèn dấu câu** được bật mặc định và đặc biệt hữu ích với PhoWhisper.
Lần đầu dùng, app tải thêm model ViBERT-CAPU ONNX INT8 khoảng 110 MB; các lần sau
chạy offline. Bước này chỉ đổi viết hoa và thêm `. , : ?`, không đổi chính tả hoặc
timestamp.

Nếu model dấu câu không tải/chạy được, job vẫn hoàn tất bằng transcript gốc và hiện
cảnh báo vàng. Có thể tắt tùy chọn để dùng đúng cách tách câu cũ.

Nguồn và license model: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
```

Add to the developer command block:

```bash
uv run python scripts/smoke_punctuation_model.py  # smoke model pin, lần đầu cần mạng
uv run python scripts/eval_punctuation.py         # boundary F1, cần fixture riêng tư
```

Do not combine this task with the already-known unrelated README port correction.

- [ ] **Step 5: Create acceptance tracker**

Create `docs/11-tasks-punctuation-restoration.md` with:

```markdown
# Punctuation Restoration — verification tracker

**Spec:** `docs/superpowers/specs/2026-07-19-punctuation-restoration-design.md`

| ID | Automated evidence | macOS arm64 | macOS x86_64 | Windows x64 |
|---|---|---|---|---|
| PR-01..PR-05 | `tests/test_punctuate.py` | — | — | — |
| PR-06..PR-07 | model smoke + hash | — | — | — |
| PR-08..PR-09 | API/UI/partial tests | — | — | — |
| PR-10 | `uv tree` no torch/tensorflow | — | — | — |
| PR-11 | notices/README review | — | — | — |
| PR-12 | ruff + full pytest | — | — | — |
| PR-13 | `scripts/eval_punctuation.py` | BLOCKED: cần fixture | BLOCKED: cần fixture | BLOCKED: cần fixture |
| PR-14 | real model smoke | — | — | — |

Chỉ thay `—`/`BLOCKED` bằng PASS khi có command, ngày, máy và output thật được ghi
bên dưới bảng. Không suy ra PASS của nền tảng khác.
```

Add below the Task 14 row in `docs/03-tasks.md`:

```markdown
| 15 | Phục hồi dấu câu ViBERT-CAPU ONNX | 🔵 | Xem `docs/11-tasks-punctuation-restoration.md`; chưa nghiệm thu đủ PR-13/PR-14 |
```

Do not mark the feature fully accepted while PR-13/PR-14 platforms remain blocked.

- [ ] **Step 6: Run full automated verification**

```bash
uv run ruff check .
uv run pytest tests/ -v
uv run python scripts/smoke_punctuation_model.py
if uv tree | rg -i '(^|[- ])(torch|tensorflow)( |$)'; then exit 1; else echo "no torch/tensorflow"; fi
git diff --check
```

Expected: ruff clean; default test suite passes without downloading models; cached
model smoke passes; dependency gate prints `no torch/tensorflow`; diff check clean.

- [ ] **Step 7: Run boundary evaluation when fixture exists**

```bash
uv run python scripts/eval_punctuation.py
```

Expected: exit 0, improvement ≥10 points, lexical WER exactly 0. If fixture is absent,
record PR-13 as BLOCKED rather than inventing a quality result.

- [ ] **Step 8: Inspect staged scope and commit Task 9**

```bash
git add scripts/eval_punctuation.py THIRD_PARTY_NOTICES.md \
  docs/11-tasks-punctuation-restoration.md eval/README.md .gitignore README.md docs/03-tasks.md
git diff --cached --check
git diff --cached --name-status
git commit -m "docs: verify punctuation restoration release gates" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: only evaluation/docs/tracker files are staged. The feature is implementation-
complete when automated gates pass; release acceptance remains honestly BLOCKED for
any platform/fixture not actually verified.

## Final implementation handoff checklist

- [ ] `git status --short` reviewed; unrelated dirty files remain preserved.
- [ ] `git log --oneline` shows one scoped commit per task.
- [ ] PR-01…PR-12 have automated evidence.
- [ ] PR-13 has a real fixture result or explicit BLOCKED state.
- [ ] PR-14 lists separate evidence for each target platform or explicit BLOCKED state.
- [ ] No claim of v0.1.0 release/tag until the original Task 14 and this tracker's
      release gates are satisfied.

## Amendments sau review (2026-07-23)

Plan này đã thực thi xong; review hồi cứu tìm ra 5 defect, được sửa theo
`docs/superpowers/plans/2026-07-23-punctuation-review-fixes.md`. Khi đọc lại plan gốc,
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
