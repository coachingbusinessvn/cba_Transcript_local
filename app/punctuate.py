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
