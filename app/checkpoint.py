"""Checkpoint transcript từng phần ra đĩa (JSONL).

File dài chạy hàng giờ trên CPU — nếu process chết giữa chừng, partial.jsonl
giữ lại toàn bộ segment đã transcript xong để server dựng kết quả "một phần"
thay vì mất trắng. Mỗi dòng một JSON {start, end, text}; dòng cuối có thể bị
cắt dở khi crash nên parser bỏ qua dòng hỏng.
"""
import json
from pathlib import Path

from .transcribe import Word


def append_words(path: Path, words: list[Word]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for w in words:
            f.write(
                json.dumps(
                    {"start": w.start, "end": w.end, "text": w.text},
                    ensure_ascii=False,
                )
                + "\n"
            )


def load_words(path: Path) -> list[Word]:
    words: list[Word] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            words.append(Word(float(d["start"]), float(d["end"]), str(d["text"])))
        except (ValueError, KeyError, TypeError):
            continue  # dòng bị cắt dở lúc crash — bỏ qua
    return words
