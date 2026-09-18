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

# Auto-cluster: threshold CÀNG LỚN → CÀNG ÍT người nói (sherpa-onnx FastClustering).
# 0.7 dễ tách hàng chục/trăm "speaker" trên hội thoại dài + embedding ồn (model SV tiếng Trung).
_AUTO_CLUSTER_THRESHOLD = 0.92
# Khi user cố định số người, threshold bị bỏ qua nếu num_clusters > 0.
_FIXED_CLUSTER_THRESHOLD = 0.5
# Hậu xử lý auto: gộp speaker chiếm < 3% tổng thời gian nói, và trần 8 người.
_MIN_SPEAKER_SHARE = 0.03
_MAX_AUTO_SPEAKERS = 8


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: int  # 0-based


# Hash chốt bằng cách tải một lần rồi ghi lại (trust-on-first-use): bắt được
# tải dở, proxy chèn nội dung, và việc upstream lặng lẽ thay file.
_SEG_SHA256 = "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488"
_EMB_SHA256 = "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"
_DOWNLOAD_TIMEOUT = 300  # giây, cho mỗi thao tác đọc socket


def _download(url: str, dest: Path, sha256: str) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as resp, tmp.open("wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    actual = config.sha256_file(tmp)
    if actual != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Model diarization tải về sai SHA-256 (nhận {actual[:12]}…). "
            "Hãy thử lại; nếu vẫn lỗi thì nguồn tải đã thay đổi."
        )
    # replace() chứ không phải rename(): trên Windows, rename lên dest đã tồn
    # tại ném FileExistsError (vd archive sót lại từ lần tải bị kill giữa
    # chừng) — replace ghi đè giống POSIX trên mọi OS.
    tmp.replace(dest)


def ensure_models() -> tuple[Path, Path]:
    """Tải model diarization lần đầu (~30 MB tổng), trả về (segmentation, embedding)."""
    d = config.data_dir() / "diarization"
    d.mkdir(parents=True, exist_ok=True)

    seg_model = d / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    if not seg_model.exists():
        archive = d / "segmentation.tar.bz2"
        _download(_SEG_URL, archive, _SEG_SHA256)
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(d, filter="data")  # chặn path traversal + hết deprecation 3.14
        archive.unlink()

    emb_model = d / "3dspeaker_eres2net_base_16k.onnx"
    if not emb_model.exists():
        _download(_EMB_URL, emb_model, _EMB_SHA256)

    return seg_model, emb_model


def _speaker_durations(turns: list[SpeakerTurn]) -> dict[int, float]:
    dur: dict[int, float] = {}
    for t in turns:
        dur[t.speaker] = dur.get(t.speaker, 0.0) + max(0.0, t.end - t.start)
    return dur


def _renumber(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
    """Đánh lại id speaker liên tục 0..K-1 theo thứ tự xuất hiện."""
    mapping: dict[int, int] = {}
    out: list[SpeakerTurn] = []
    for t in turns:
        if t.speaker not in mapping:
            mapping[t.speaker] = len(mapping)
        out.append(SpeakerTurn(t.start, t.end, mapping[t.speaker]))
    return out


def merge_minor_speakers(
    turns: list[SpeakerTurn],
    *,
    min_share: float = _MIN_SPEAKER_SHARE,
    max_speakers: int = _MAX_AUTO_SPEAKERS,
) -> list[SpeakerTurn]:
    """Gộp speaker 'lạ' (nói rất ít) vào người nói kề trước/sau theo thời gian.

    Dùng sau clustering tự động — tránh 50–150 nhãn khi thực tế chỉ 2–3 người.
    """
    if not turns:
        return turns

    dur = _speaker_durations(turns)
    total = sum(dur.values()) or 1.0
    # Giữ speaker đủ dài; nếu vẫn quá nhiều thì chỉ giữ top max_speakers theo thời lượng
    keep = {s for s, d in dur.items() if d / total >= min_share}
    if len(keep) > max_speakers:
        ranked = sorted(dur.items(), key=lambda x: -x[1])
        keep = {s for s, _ in ranked[:max_speakers]}
    if not keep:
        # fallback: giữ 1–2 người nói nhiều nhất
        ranked = sorted(dur.items(), key=lambda x: -x[1])
        keep = {s for s, _ in ranked[: min(2, len(ranked))]}

    if keep == set(dur.keys()):
        return _renumber(turns)

    # Gán lại: ưu tiên speaker của turn liền trước còn hợp lệ, không thì turn sau
    n = len(turns)
    new_spk = [t.speaker for t in turns]

    # pass 1: forward fill from previous kept
    last_kept: int | None = None
    for i in range(n):
        if new_spk[i] in keep:
            last_kept = new_spk[i]
        elif last_kept is not None:
            new_spk[i] = last_kept

    # pass 2: backward fill for prefix that had no previous kept
    next_kept: int | None = None
    for i in range(n - 1, -1, -1):
        if new_spk[i] in keep:
            next_kept = new_spk[i]
        elif next_kept is not None:
            new_spk[i] = next_kept

    # pass 3: bất kỳ id còn lại ngoài keep → map về speaker dài nhất
    major = max(keep, key=lambda s: dur.get(s, 0.0))
    for i in range(n):
        if new_spk[i] not in keep:
            new_spk[i] = major

    merged = [SpeakerTurn(t.start, t.end, new_spk[i]) for i, t in enumerate(turns)]
    return _renumber(merged)


def diarize(
    wav16k_path: Path,
    num_speakers: int = 0,
    progress_cb: Callable[[float], None] | None = None,
) -> list[SpeakerTurn]:
    """Chạy diarization trên WAV 16kHz mono. num_speakers=0 nghĩa là tự đoán."""
    import sherpa_onnx

    from .media import read_wav16k_float32

    seg_model, emb_model = ensure_models()
    auto = num_speakers <= 0
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg_model)
            ),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb_model)),
        clustering=sherpa_onnx.FastClusteringConfig(
            # num_clusters > 0: ép đúng số người (khuyến nghị cho họp 2–3 người)
            num_clusters=num_speakers if not auto else -1,
            # auto: threshold lớn hơn → ít cluster hơn (doc sherpa-onnx)
            threshold=_AUTO_CLUSTER_THRESHOLD if auto else _FIXED_CLUSTER_THRESHOLD,
        ),
        min_duration_on=0.3,
        min_duration_off=0.6,
    )
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    samples = read_wav16k_float32(wav16k_path)

    # Callback diarize gọi rất dày — throttle để UI/server không bị spam
    _last_frac = [-1.0]

    def _cb(processed: int, total: int) -> int:
        if progress_cb and total > 0:
            frac = processed / total
            if frac - _last_frac[0] >= 0.02 or frac >= 1.0:
                _last_frac[0] = frac
                progress_cb(frac)
        return 0

    result = sd.process(samples, callback=_cb).sort_by_start_time()
    turns = [SpeakerTurn(r.start, r.end, r.speaker) for r in result]

    if auto:
        turns = merge_minor_speakers(turns)
    else:
        turns = _renumber(turns)
    return turns
