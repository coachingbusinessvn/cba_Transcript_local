"""Phục hồi dấu câu tiếng Việt bằng ViBERT-CAPU ONNX, best-effort."""

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

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
    cached = config.punctuation_is_downloaded()
    if not cached:
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
    if not cached:
        _write_manifest(root)
    return root


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


log = logging.getLogger("vitranscript")
_TARGET_PUNCTUATION = ".,:?"
_SPAN_RE = re.compile(r"\s+|[^\s]+")
_WARNING = "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."
_PARTIAL_WARNING = (
    "Một số đoạn không phục hồi được dấu câu; các đoạn còn lại vẫn được xử lý."
)


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
        for before, after in zip(original, restored, strict=True)
    )


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
) -> tuple[list[str], int]:
    predictions = []
    furthest = 0
    failed = 0
    ranges = _chunk_ranges(len(pieces))
    for start, end in ranges:
        try:
            feeds = _encode_chunk(runtime, pieces[start:end])
            logits = runtime.session.run(["logits", "detect_logits"], feeds)[0]
            label_ids = np.argmax(logits[0], axis=-1).tolist()
            actions = [runtime.labels[index] for index in label_ids]
            if len(actions) != end - start:
                raise RuntimeError("Model dấu câu trả sai số word")
        except Exception as e:
            # Một chunk hỏng (ví dụ tokenizer nuốt trọn một token lạ) không được
            # làm mất dấu câu của cả file — _choose_overlapping mặc định $KEEP.
            # File dài có thể có hàng nghìn chunk (stride 36): chỉ log traceback
            # đầy đủ cho chunk lỗi đầu tiên, các chunk sau chỉ log 1 dòng thông
            # điệp — tránh làm ngập console người dùng đang theo dõi.
            if failed == 0:
                log.exception("Bỏ qua chunk dấu câu %d-%d", start, end)
            else:
                log.warning("Bỏ qua chunk dấu câu %d-%d: %s", start, end, e)
            failed += 1
            continue
        predictions.append((start, end, actions))
        furthest = max(furthest, end)
        if progress_cb:
            progress_cb(furthest / len(pieces))
    if ranges and failed == len(ranges):
        raise RuntimeError("Toàn bộ chunk dấu câu đều lỗi")
    return _choose_overlapping(len(pieces), predictions), failed


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

        failed_chunks = 0
        # Iterative refinement kiểu GECToR: model được huấn luyện để tag nhiều vòng,
        # pass sau đọc text đã được hoa/chấm ở pass trước nên bắt thêm được ranh giới
        # câu. Thoát sớm ngay khi một pass không đổi gì, nên chi phí thường là 2 pass
        # chứ không phải 3. progress_cb chỉ gắn vào pass đầu để thanh tiến trình
        # không nhảy lùi.
        for iteration in range(3):
            actions, failed = _predict_actions(
                pieces, runtime, monotonic if iteration == 0 else None
            )
            failed_chunks = max(failed_chunks, failed)
            changed = False
            for piece, action in zip(pieces, actions, strict=True):
                changed = _apply_safe_action(piece, action) or changed
            if not changed:
                break
        restored = _rebuild_words(original, layouts, pieces)
        if not _invariants_hold(original, restored):
            raise RuntimeError("Invariant punctuation bị vi phạm")
        if progress_cb:
            progress_cb(1.0)
        return PunctuationResult(
            restored, True, _PARTIAL_WARNING if failed_chunks else None
        )
    except Exception:
        log.exception("Không thể phục hồi dấu câu")
        return PunctuationResult(original, False, _WARNING)
