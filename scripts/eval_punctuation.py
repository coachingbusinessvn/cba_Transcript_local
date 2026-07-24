"""Đo boundary F1 của punctuation trên fixture word-aligned riêng tư."""

import json
import sys
from pathlib import Path

from jiwer import wer

sys.path.insert(0, str(Path(__file__).parent.parent))

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
