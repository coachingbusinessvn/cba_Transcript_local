"""Ghép từ thành câu (dựa trên dấu câu Whisper tự chèn) và gán người nói."""
from dataclasses import dataclass

from .diarize import SpeakerTurn
from .transcribe import Word

_SENTENCE_END = (".", "!", "?", "…")
_MAX_SENTENCE_SECONDS = 15.0
_MAX_SENTENCE_WORDS = 40
_GAP_BREAK_SECONDS = 1.2


@dataclass
class Sentence:
    start: float
    end: float
    text: str
    speaker: int | None = None  # 0-based, None nếu không chạy diarization


def build_sentences(words: list[Word]) -> list[Sentence]:
    sentences: list[Sentence] = []
    buf: list[Word] = []

    def flush():
        if buf:
            text = "".join(w.text for w in buf).strip()
            text = " ".join(text.split())
            if text:
                sentences.append(Sentence(buf[0].start, buf[-1].end, text))
            buf.clear()

    for w in words:
        if buf and w.start - buf[-1].end > _GAP_BREAK_SECONDS:
            flush()
        buf.append(w)
        too_long = (
            buf[-1].end - buf[0].start > _MAX_SENTENCE_SECONDS
            or len(buf) >= _MAX_SENTENCE_WORDS
        )
        if w.text.rstrip().endswith(_SENTENCE_END) or too_long:
            flush()
    flush()
    return sentences


def assign_speakers(sentences: list[Sentence], turns: list[SpeakerTurn]) -> None:
    """Gán mỗi câu cho người nói có thời gian chồng lấn nhiều nhất."""
    if not turns:
        return
    for i, s in enumerate(sentences):
        overlap: dict[int, float] = {}
        for t in turns:
            ov = min(s.end, t.end) - max(s.start, t.start)
            if ov > 0:
                overlap[t.speaker] = overlap.get(t.speaker, 0.0) + ov
        if overlap:
            s.speaker = max(overlap, key=overlap.get)
        else:
            # câu không trùng với đoạn diarization nào → theo câu liền trước
            s.speaker = sentences[i - 1].speaker if i > 0 else 0
