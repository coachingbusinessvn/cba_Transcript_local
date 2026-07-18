"""Transcript bằng faster-whisper (CTranslate2, CPU int8)."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import config

# Cache model theo process: tránh load lại ~0.5–3GB mỗi job (RAM + thời gian).
# v1 chỉ giữ 1 model gần nhất — đổi model_key sẽ giải phóng tham chiếu cũ.
_MODEL_CACHE: dict[str, object] = {}


@dataclass
class Word:
    start: float
    end: float
    text: str


def load_model(model_key: str):
    """Nạp WhisperModel (CPU int8). Lần hai cùng model_key trả về instance đã cache."""
    if model_key in _MODEL_CACHE:
        return _MODEL_CACHE[model_key]

    from faster_whisper import WhisperModel

    source = config.MODEL_REGISTRY[model_key]["source"]
    model = WhisperModel(
        source,
        device="cpu",
        compute_type="int8",
        download_root=str(config.models_dir()),
    )
    _MODEL_CACHE.clear()  # chỉ giữ 1 model trong RAM (máy CPU yếu)
    _MODEL_CACHE[model_key] = model
    return model


def transcribe(
    model,
    wav_path: Path,
    duration: float,
    language: str = "vi",
    beam_size: int = 5,
    initial_prompt: str | None = None,
    hotwords: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
    segment_cb: Callable[[list[Word]], None] | None = None,
) -> list[Word]:
    """Chạy transcript, trả về danh sách từ kèm timestamp (giây).

    segment_cb (nếu có) được gọi với danh sách Word của TỪNG segment ngay khi
    segment đó xong — dùng để checkpoint ra đĩa cho file dài.
    """
    segments, _info = model.transcribe(
        str(wav_path),
        language=None if language == "auto" else language,
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        initial_prompt=initial_prompt or None,
        hotwords=hotwords or None,
        condition_on_previous_text=False,
    )

    words: list[Word] = []
    for seg in segments:
        if seg.words:
            new = [Word(w.start, w.end, w.word) for w in seg.words]
        else:
            new = [Word(seg.start, seg.end, seg.text)]
        words.extend(new)
        if segment_cb:
            segment_cb(new)
        if progress_cb and duration > 0:
            progress_cb(min(seg.end / duration, 1.0))
    return words
