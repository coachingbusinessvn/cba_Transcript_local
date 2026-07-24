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


def ffprobe_path() -> str:
    """Như ffmpeg_path nhưng cho ffprobe (static-ffmpeg trả về cặp (ffmpeg, ffprobe))."""
    found = shutil.which("ffprobe")
    if found:
        return found
    import static_ffmpeg.run

    return static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()[1]


def duration_seconds(path: Path) -> float | None:
    """Thời lượng file (giây) qua ffprobe. Trả về None nếu không đọc được — caller tự quyết."""
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


# 1 giờ: dư cho file 4h convert trên CPU yếu, nhưng chặn được ffmpeg treo vĩnh viễn.
_FFMPEG_TIMEOUT = 3600


def _run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_path(), "-hide_banner", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ffmpeg chạy quá {_FFMPEG_TIMEOUT // 60} phút mà chưa xong — đã dừng. "
            "File có thể bị hỏng."
        ) from e
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


def read_wav16k_float32(wav_path: Path, _chunk_frames: int = 960_000):
    """Đọc WAV 16kHz mono thành mảng float32 [-1, 1] cho sherpa-onnx.

    Đọc theo khối (mặc định 60s/khối) vào mảng float32 cấp phát sẵn:
    file 3 giờ chỉ tốn ~4 B/sample thay vì ~10 B/sample đỉnh như đọc một cục
    (bytes int16 + bản astype + bản kết quả phép chia).
    """
    import numpy as np

    with wave.open(str(wav_path), "rb") as w:
        # Không dùng assert: sẽ bị bỏ qua khi chạy python -O, khiến WAV sai định dạng
        # bị đọc thành mẫu rác cho diarization.
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("WAV phải là 16kHz mono")
        n = w.getnframes()
        out = np.empty(n, dtype=np.float32)
        pos = 0
        while pos < n:
            data = w.readframes(min(_chunk_frames, n - pos))
            block = np.frombuffer(data, dtype=np.int16)
            if len(block) == 0:
                # Header khai nhiều frame hơn dữ liệu thực (file bị cắt dở).
                # Không thoát ở đây thì pos đứng yên và vòng lặp chạy mãi.
                # .copy(): out[:pos] là view — nếu giữ view thì mảng gốc (có thể
                # rất lớn, vd header khai 4h nhưng data thực chỉ 1 phút) vẫn bị
                # pin trong bộ nhớ dù kết quả trả về nhỏ hơn nhiều.
                out = out[:pos].copy()
                break
            out[pos : pos + len(block)] = block
            pos += len(block)
    out /= 32768.0  # in-place, không tạo mảng mới
    return out
