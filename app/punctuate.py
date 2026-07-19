"""Phục hồi dấu câu tiếng Việt bằng ViBERT-CAPU ONNX, best-effort."""

import hashlib
import json
import os
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
