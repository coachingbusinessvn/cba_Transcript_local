"""Xử lý audio/video bằng ffmpeg: convert video sang audio, chuẩn hóa về WAV 16kHz mono."""
import shutil
import subprocess
import wave
from pathlib import Path

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".wma", ".opus"}
VIDEO_EXTS = {".mov", ".mp4", ".mkv", ".avi", ".webm", ".m4v"}


def ffmpeg_path() -> str:
    """Ưu tiên ffmpeg có sẵn trên máy; nếu không có thì dùng bản static-ffmpeg tải qua pip."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    import static_ffmpeg.run

    return static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()[0]


def _run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_path(), "-hide_banner", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {proc.stderr[-2000:]}")


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS | VIDEO_EXTS


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Tách audio từ video sang m4a (copy stream nếu được, nếu không thì encode AAC)."""
    try:
        _run_ffmpeg(["-i", str(video_path), "-vn", "-acodec", "copy", str(out_path)])
    except RuntimeError:
        _run_ffmpeg(["-i", str(video_path), "-vn", "-c:a", "aac", "-b:a", "192k", str(out_path)])
    return out_path


def to_wav16k(input_path: Path, out_path: Path) -> Path:
    """Chuẩn hóa mọi định dạng về WAV 16kHz mono — đầu vào chung cho transcript và diarization."""
    _run_ffmpeg(
        ["-i", str(input_path), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(out_path)]
    )
    return out_path


def wav_duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav16k_float32(wav_path: Path):
    """Đọc WAV 16kHz mono thành mảng float32 [-1, 1] cho sherpa-onnx."""
    import numpy as np

    with wave.open(str(wav_path), "rb") as w:
        # Không dùng assert: sẽ bị bỏ qua khi chạy python -O, khiến WAV sai định dạng
        # bị đọc thành mẫu rác cho diarization.
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("WAV phải là 16kHz mono")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
