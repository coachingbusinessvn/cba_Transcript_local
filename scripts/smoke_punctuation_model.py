"""Smoke ViBERT-CAPU ONNX đã pin; lần đầu cần mạng."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
