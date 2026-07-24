"""Ghép toàn bộ pipeline: convert → transcribe → punctuate → diarize → glossary → tách câu."""
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from . import checkpoint, config, diarize, glossary, media, punctuate, segment, transcribe

ProgressCb = Callable[[str, float, str], None]  # (stage, percent 0-100, message)


def run(
    input_path: Path,
    work_dir: Path,
    model_key: str,
    language: str = "vi",
    enable_punctuation: bool = True,
    enable_diarization: bool = True,
    num_speakers: int = 0,
    glossary_text: str = "",
    progress: ProgressCb | None = None,
) -> dict:
    """Chạy toàn bộ pipeline, trả về dict kết quả (sentences + thông tin phụ)."""

    def report(stage: str, pct: float, msg: str):
        if progress:
            progress(stage, pct, msg)

    work_dir.mkdir(parents=True, exist_ok=True)
    gloss = glossary.parse(glossary_text)

    # 1. Convert: video → audio, rồi chuẩn hóa WAV 16kHz mono
    report("convert", 2, "Đang chuẩn hóa audio…")
    extracted_audio = None
    if media.is_video(input_path):
        extracted_audio = media.extract_audio(input_path, work_dir / (input_path.stem + ".m4a"))
    wav = media.to_wav16k(extracted_audio or input_path, work_dir / "audio16k.wav")
    duration = media.wav_duration_seconds(wav)

    # 2. Load model (lần đầu sẽ tải về, có thể mất vài phút)
    size = config.MODEL_REGISTRY[model_key]["size"]
    downloaded = config.model_is_downloaded(model_key)
    report("model", 6, "Đang nạp model…" if downloaded
           else f"Lần đầu dùng model này: đang tải về ({size}), có thể mất vài phút…")
    model = transcribe.load_model(model_key)

    # 3. Transcribe (chiếm phần lớn thời gian) — checkpoint từng segment ra đĩa
    partial_path = work_dir / "partial.jsonl"
    partial_path.unlink(missing_ok=True)  # job chạy lại trong cùng dir không dính dữ liệu cũ
    report("transcribe", 12, "Đang chuyển giọng nói thành văn bản…")
    settings = config.load_settings()
    words = transcribe.transcribe(
        model, wav, duration,
        language=language,
        beam_size=int(settings.get("beam_size", 5)),
        hotwords=gloss.hotwords or None,
        progress_cb=lambda f: report(
            "transcribe", 12 + f * 54, f"Đang chuyển giọng nói thành văn bản… {int(f * 100)}%"
        ),
        segment_cb=lambda ws: checkpoint.append_words(partial_path, ws),
    )

    # 3b. Phục hồi dấu câu (best-effort; trước tách câu)
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

    # 4. Diarization
    turns = []
    if enable_diarization:
        report("diarize", 72, "Đang phân biệt người nói…")
        turns = diarize.diarize(
            wav, num_speakers=num_speakers,
            progress_cb=lambda f: report(
                "diarize", 72 + f * 20, f"Đang phân biệt người nói… {int(f * 100)}%"
            ),
        )

    # 5. Tách câu + sửa theo glossary
    report("finalize", 94, "Đang tách câu và sửa từ khóa…")
    sentences = segment.build_sentences(words)
    for s in sentences:
        s.text = glossary.correct(s.text, gloss)
    if turns:
        segment.assign_speakers(sentences, turns)

    n_speakers = len({s.speaker for s in sentences if s.speaker is not None})
    report("done", 100, "Hoàn tất!")
    return {
        "sentences": [asdict(s) for s in sentences],
        "duration": duration,
        "num_speakers": n_speakers,
        "extracted_audio": str(extracted_audio) if extracted_audio else None,
        "model": model_key,
        "punctuation": punctuation_meta,
    }
