"""Phân biệt người nói (speaker diarization) bằng sherpa-onnx.

Dùng model pyannote segmentation 3.0 + 3D-Speaker embedding đã convert sang ONNX:
chạy hoàn toàn local, không cần PyTorch, không cần tài khoản Hugging Face.
"""
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import config

_SEG_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
# Lưu ý: "recongition" là lỗi chính tả có thật trong tên release của sherpa-onnx.
_EMB_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: int  # 0-based


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)


def ensure_models() -> tuple[Path, Path]:
    """Tải model diarization lần đầu (~30 MB tổng), trả về (segmentation, embedding)."""
    d = config.data_dir() / "diarization"
    d.mkdir(parents=True, exist_ok=True)

    seg_model = d / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    if not seg_model.exists():
        archive = d / "segmentation.tar.bz2"
        _download(_SEG_URL, archive)
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(d)
        archive.unlink()

    emb_model = d / "3dspeaker_eres2net_base_16k.onnx"
    if not emb_model.exists():
        _download(_EMB_URL, emb_model)

    return seg_model, emb_model


def diarize(
    wav16k_path: Path,
    num_speakers: int = 0,
    progress_cb: Callable[[float], None] | None = None,
) -> list[SpeakerTurn]:
    """Chạy diarization trên WAV 16kHz mono. num_speakers=0 nghĩa là tự đoán."""
    import sherpa_onnx

    from .media import read_wav16k_float32

    seg_model, emb_model = ensure_models()
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg_model)
            ),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb_model)),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers if num_speakers > 0 else -1,
            threshold=0.7,
        ),
        min_duration_on=0.2,
        min_duration_off=0.5,
    )
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    samples = read_wav16k_float32(wav16k_path)

    def _cb(processed: int, total: int) -> int:
        if progress_cb and total > 0:
            progress_cb(processed / total)
        return 0

    result = sd.process(samples, callback=_cb).sort_by_start_time()
    return [SpeakerTurn(r.start, r.end, r.speaker) for r in result]
