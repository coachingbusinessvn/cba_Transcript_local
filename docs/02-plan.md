# Plan triển khai: ViTranscript — transcript tiếng Việt local-first

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ứng dụng web-UI local cho phép chọn file audio/video, transcript tiếng Việt bằng faster-whisper, phân biệt người nói bằng sherpa-onnx, sửa từ khóa theo glossary, xuất DOCX/XLSX/SRT/TXT — cài đặt 1-click trên Mac/Windows.

**Architecture:** Core pipeline thuần Python (convert → transcribe → diarize → correct → segment) tách khỏi lớp giao tiếp; FastAPI phục vụ 1 trang HTML tĩnh và chạy job trong thread nền, client poll tiến trình. Không PyTorch — chỉ CTranslate2 (faster-whisper) và ONNX Runtime (sherpa-onnx) để bộ cài nhẹ và ít lỗi.

**Tech Stack:** Python 3.12 (qua `uv`), faster-whisper, sherpa-onnx, FastAPI + uvicorn, python-docx, openpyxl, rapidfuzz, static-ffmpeg, numpy. Dev: pytest, ruff, jiwer.

## Global Constraints

- `requires-python = ">=3.10,<3.13"` (installer pin 3.12)
- KHÔNG thêm dependency kéo theo PyTorch/TensorFlow
- Máy mục tiêu: macOS arm64, macOS x86_64, Windows x64 CPU-only — mọi lựa chọn phải chạy được CPU int8
- Toàn bộ text hiển thị cho người dùng bằng tiếng Việt; riêng file `.bat` viết không dấu (tránh lỗi codepage)
- Server chỉ bind `127.0.0.1`; dữ liệu người dùng lưu ở thư mục data theo chuẩn OS, không ghi vào thư mục cài đặt
- **v1 chỉ 1 job transcript chạy tại một thời điểm** (server 409 nếu bận); cache tối đa 1 WhisperModel trong process
- **Quy trình mỗi task:** làm xong → `uv run ruff check .` sạch lỗi → chạy bước verify của task → `git add` các file của task + `git commit -m "<type>: <mô tả>"` (type: feat/test/docs/chore). Commit message kết thúc bằng dòng `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- **Commit `uv.lock`** ngay sau lần `uv sync` đầu tiên — máy người dùng phải cài đúng phiên bản đã test
- Model registry đã verify tồn tại ngày 2026-07-17: `diepho/PhoWhisper-small-ct2`, `diepho/PhoWhisper-medium-ct2`, `kiendt/PhoWhisper-large-ct2`, `deepdml/faster-whisper-large-v3-turbo-ct2`
- URL model diarization (đã verify HTTP 200) ghi trong code Task 4 — tag release `speaker-recongition-models` sai chính tả là CỐ Ý (lỗi của upstream, không được "sửa")

---

### Task 0: Khung dự án

**Files:**
- Create: `pyproject.toml`, `app/__init__.py` (rỗng), `.python-version` (nội dung: `3.12`)

**Interfaces:**
- Produces: package `app` import được; lệnh `uv sync` / `uv run` hoạt động; cấu hình ruff dùng chung.

- [ ] **Step 1: Viết `pyproject.toml`**

```toml
[project]
name = "vi-transcript"
version = "0.1.0"
description = "Ứng dụng local-first chuyển hội thoại tiếng Việt thành văn bản (transcript) với timestamp và phân biệt người nói"
requires-python = ">=3.10,<3.13"
dependencies = [
    "faster-whisper>=1.1.0",
    "sherpa-onnx>=1.10.30",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "python-multipart>=0.0.9",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.2",
    "rapidfuzz>=3.6",
    "static-ffmpeg>=2.7",
    "huggingface-hub>=0.23",
    "numpy>=1.26",  # dùng trực tiếp trong media.read_wav16k_float32 — khai báo tường minh, không phụ thuộc transitive
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.4", "jiwer>=3.0"]

[tool.uv]
package = false

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
```

- [ ] **Step 2: Tạo `app/__init__.py` rỗng và `.python-version` chứa `3.12`**
- [ ] **Step 3: Verify** — Run: `uv sync`. Expected: tạo `.venv/` + `uv.lock`, không lỗi. Run: `uv run ruff check .` → sạch.
- [ ] **Step 4: Commit** — `git add pyproject.toml uv.lock .python-version app/__init__.py && git commit -m "chore: khung du an uv + ruff"`

### Task 1: Config & model registry

**Files:**
- Create: `app/config.py`

**Interfaces:**
- Produces (các task sau dùng đúng các tên này):
  - `MODEL_REGISTRY: dict[str, dict]` — key → `{source, label, size}`
  - `data_dir() / models_dir() / jobs_dir() -> Path`
  - `load_settings() -> dict` / `save_settings(dict) -> dict` (keys hợp lệ: `model`, `language`, `beam_size`)
  - `load_glossary_text() -> str` / `save_glossary_text(str)`
  - `model_is_downloaded(model_key: str) -> bool`

- [ ] **Step 1: Viết `app/config.py`**

```python
"""Cấu hình chung: đường dẫn dữ liệu, danh sách model, settings người dùng."""
import json
import os
import sys
from pathlib import Path

APP_NAME = "ViTranscript"

# Danh sách model transcript. Tất cả đều ở định dạng CTranslate2, chạy trên
# faster-whisper, CPU int8 — không cần GPU, không cần tài khoản Hugging Face.
MODEL_REGISTRY = {
    "phowhisper-small": {
        "source": "diepho/PhoWhisper-small-ct2",
        "label": "PhoWhisper Small — nhanh, tiếng Việt tốt (mặc định)",
        "size": "~490 MB",
    },
    "phowhisper-medium": {
        "source": "diepho/PhoWhisper-medium-ct2",
        "label": "PhoWhisper Medium — chính xác hơn, chậm hơn ~2x",
        "size": "~1.5 GB",
    },
    "phowhisper-large": {
        "source": "kiendt/PhoWhisper-large-ct2",
        "label": "PhoWhisper Large — chính xác nhất cho tiếng Việt, chậm",
        "size": "~3 GB",
    },
    "large-v3-turbo": {
        "source": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "label": "Whisper Large-v3 Turbo — tốt khi xen nhiều tiếng Anh",
        "size": "~1.6 GB",
    },
    "whisper-small": {
        "source": "small",
        "label": "Whisper Small gốc — đa ngôn ngữ, nhẹ",
        "size": "~490 MB",
    },
}

DEFAULT_SETTINGS = {
    "model": "phowhisper-small",
    "language": "vi",
    "beam_size": 5,
}


def data_dir() -> Path:
    """Thư mục lưu model, settings, glossary — theo chuẩn từng hệ điều hành."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def jobs_dir() -> Path:
    d = data_dir() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(_settings_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if s.get("model") not in MODEL_REGISTRY:
        s["model"] = DEFAULT_SETTINGS["model"]
    return s


def save_settings(new_values: dict) -> dict:
    s = load_settings()
    s.update({k: v for k, v in new_values.items() if k in DEFAULT_SETTINGS})
    _settings_path().write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return s


def _glossary_path() -> Path:
    return data_dir() / "glossary.txt"


def load_glossary_text() -> str:
    try:
        return _glossary_path().read_text(encoding="utf-8")
    except OSError:
        return ""


def save_glossary_text(text: str) -> None:
    _glossary_path().write_text(text, encoding="utf-8")


def model_is_downloaded(model_key: str) -> bool:
    """Model coi như đã tải nếu tồn tại model.bin trong cache Hugging Face local."""
    source = MODEL_REGISTRY[model_key]["source"]
    if "/" not in source:  # tên built-in của faster-whisper (vd. "small")
        source = f"Systran/faster-whisper-{source}"
    cache_name = "models--" + source.replace("/", "--")
    root = models_dir() / cache_name
    return any(root.rglob("model.bin")) if root.exists() else False
```

- [ ] **Step 2: Verify** — `uv run python -c "from app import config; print(config.load_settings())"`. Expected: in dict với `model: phowhisper-small`. Test kỹ hơn ở Task 8 (`test_settings_roundtrip`).
- [ ] **Step 3: Commit** — `git commit -m "feat: config va model registry"`

### Task 2: Media/ffmpeg

**Files:**
- Create: `app/media.py`

**Interfaces:**
- Produces:
  - `AUDIO_EXTS`, `VIDEO_EXTS: set[str]`; `is_video(Path) -> bool`; `is_supported(Path) -> bool`
  - `extract_audio(video_path, out_path) -> Path` — tách audio video → m4a
  - `to_wav16k(input_path, out_path) -> Path` — chuẩn hóa WAV 16kHz mono
  - `wav_duration_seconds(Path) -> float`; `read_wav16k_float32(Path) -> np.ndarray`

- [ ] **Step 1: Viết `app/media.py`**

```python
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
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "WAV phải là 16kHz mono"
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
```

- [ ] **Step 2: Verify nhanh** — `uv run python -c "from pathlib import Path; from app.media import is_video, is_supported; assert is_video(Path('a.MOV')); assert is_supported(Path('b.mp3')); print('ok')"`. Verify convert thật ở Task 12.
- [ ] **Step 3: Commit** — `git commit -m "feat: convert audio/video bang ffmpeg"`

### Task 3: Transcribe (faster-whisper)

**Files:**
- Create: `app/transcribe.py`

**Interfaces:**
- Consumes: `config.MODEL_REGISTRY`, `config.models_dir()`
- Produces:
  - `Word(start: float, end: float, text: str)` (dataclass)
  - `load_model(model_key) -> WhisperModel` (CPU, int8, `download_root=models_dir()`; **cache 1 model/process**, đổi key thì thay cache)
  - `transcribe(model, wav_path, duration, language="vi", beam_size=5, initial_prompt=None, hotwords=None, progress_cb=None) -> list[Word]`

- [ ] **Step 1: Viết `app/transcribe.py`**

```python
"""Transcript bằng faster-whisper (CTranslate2, CPU int8)."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

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
    initial_prompt: Optional[str] = None,
    hotwords: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> list[Word]:
    """Chạy transcript, trả về danh sách từ kèm timestamp (giây)."""
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
            words.extend(Word(w.start, w.end, w.word) for w in seg.words)
        else:
            words.append(Word(seg.start, seg.end, seg.text))
        if progress_cb and duration > 0:
            progress_cb(min(seg.end / duration, 1.0))
    return words
```

- [ ] **Step 2: Verify** — `uv run python -c "import app.transcribe; print('ok')"` (chạy thật ở Task 12; tham số `hotwords` cần faster-whisper ≥1.0.2 — nếu Task 12 báo lỗi tham số, bỏ `hotwords`, dồn hết vào `initial_prompt`).
- [ ] **Step 3: Commit** — `git commit -m "feat: transcribe faster-whisper"`

### Task 4: Diarization (sherpa-onnx)

**Files:**
- Create: `app/diarize.py`

**Interfaces:**
- Consumes: `config.data_dir()`, `media.read_wav16k_float32`
- Produces:
  - `SpeakerTurn(start: float, end: float, speaker: int)` (0-based)
  - `ensure_models() -> tuple[Path, Path]` — tải ~30MB lần đầu
  - `diarize(wav16k_path, num_speakers=0, progress_cb=None) -> list[SpeakerTurn]` (0 = tự đoán)

- [ ] **Step 1: Viết `app/diarize.py`**

```python
"""Phân biệt người nói (speaker diarization) bằng sherpa-onnx.

Dùng model pyannote segmentation 3.0 + 3D-Speaker embedding đã convert sang ONNX:
chạy hoàn toàn local, không cần PyTorch, không cần tài khoản Hugging Face.
"""
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

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
    progress_cb: Optional[Callable[[float], None]] = None,
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
```

- [ ] **Step 2: Verify** — `uv run python -c "import app.diarize; print('ok')"` (chạy thật + verify chữ ký API `process(samples, callback=...)` ở Task 12).
- [ ] **Step 3: Commit** — `git commit -m "feat: diarization sherpa-onnx"`

### Task 5: Glossary (sửa từ khóa 2 tầng)

**Files:**
- Create: `app/glossary.py`

**Interfaces:**
- Produces:
  - `parse(text) -> Glossary`; cú pháp mỗi dòng: `sai => đúng` hoặc `Từ Khóa`; dòng `#` là comment
  - `Glossary.replacements: list[tuple[str, str]]`, `Glossary.keywords: list[str]`, `Glossary.hotwords -> str`
  - `correct(text, glossary) -> str`

- [ ] **Step 1: Viết `app/glossary.py`**

```python
"""Từ điển sửa lỗi (glossary): thiên vị model khi decode + tự sửa sau khi transcript.

Định dạng file glossary (mỗi dòng một mục, dòng bắt đầu # là ghi chú):
  từ sai => từ đúng      : luôn thay "từ sai" bằng "từ đúng" (không phân biệt hoa thường)
  Thuật Ngữ              : từ khóa cần giữ đúng — được đưa vào hotwords của model,
                           đồng thời các cụm gần giống trong transcript sẽ bị "hút" về đúng dạng này
"""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Chữ cái ASCII + toàn bộ dải chữ có dấu tiếng Việt
_LETTER = r"A-Za-zÀ-ỹ0-9"
_FUZZY_THRESHOLD = 88


@dataclass
class Glossary:
    replacements: list[tuple[str, str]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @property
    def hotwords(self) -> str:
        """Chuỗi đưa vào tham số hotwords của faster-whisper."""
        terms = [right for _, right in self.replacements] + self.keywords
        return ", ".join(dict.fromkeys(terms))  # bỏ trùng, giữ thứ tự


def parse(text: str) -> Glossary:
    g = Glossary()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            wrong, _, right = line.partition("=>")
            wrong, right = wrong.strip(), right.strip()
            if wrong and right:
                g.replacements.append((wrong, right))
        else:
            g.keywords.append(line)
    return g


def _boundary_pattern(term: str) -> re.Pattern:
    # \b không hoạt động tốt với chữ có dấu — dùng lookaround trên dải chữ tiếng Việt
    return re.compile(
        rf"(?<![{_LETTER}]){re.escape(term)}(?![{_LETTER}])", re.IGNORECASE
    )


def _fuzzy_snap(text: str, term: str) -> str:
    """Thay các cụm từ gần giống `term` (sai chính tả nhẹ) bằng đúng `term`."""
    n = len(term.split())
    words = text.split(" ")
    if len(words) < n:
        return text
    out, i = [], 0
    while i <= len(words) - n:
        chunk = " ".join(words[i : i + n])
        core = chunk.strip(".,!?;:…\"'()")
        if core and core.lower() != term.lower() and abs(len(core) - len(term)) <= 3:
            if fuzz.ratio(core.lower(), term.lower()) >= _FUZZY_THRESHOLD:
                out.append(chunk.replace(core, term))
                i += n
                continue
        out.append(words[i])
        i += 1
    out.extend(words[i:])
    return " ".join(out)


def correct(text: str, glossary: Glossary) -> str:
    for wrong, right in glossary.replacements:
        text = _boundary_pattern(wrong).sub(right, text)
    for term in glossary.keywords:
        if len(term) >= 4:  # từ quá ngắn dễ thay nhầm
            text = _fuzzy_snap(text, term)
    return text
```

- [ ] **Step 2: Verify** — unit tests Task 8 (`test_glossary_exact_replacement_vietnamese_boundary`, `test_glossary_fuzzy_snap`, `test_glossary_no_false_positive`).
- [ ] **Step 3: Commit** — `git commit -m "feat: glossary sua tu khoa 2 tang"`

### Task 6: Tách câu + gán người nói

**Files:**
- Create: `app/segment.py`

**Interfaces:**
- Consumes: `transcribe.Word`, `diarize.SpeakerTurn`
- Produces:
  - `Sentence(start: float, end: float, text: str, speaker: int | None = None)` (dataclass)
  - `build_sentences(list[Word]) -> list[Sentence]`
  - `assign_speakers(sentences, turns) -> None` (sửa in-place)

- [ ] **Step 1: Viết `app/segment.py`**

```python
"""Ghép từ thành câu (dựa trên dấu câu Whisper tự chèn) và gán người nói."""
from dataclasses import dataclass
from typing import Optional

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
    speaker: Optional[int] = None  # 0-based, None nếu không chạy diarization


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
```

- [ ] **Step 2: Verify** — unit tests Task 8 (`test_build_sentences_*`, `test_assign_speakers_by_overlap`).
- [ ] **Step 3: Commit** — `git commit -m "feat: tach cau va gan nguoi noi"`

### Task 7: Export DOCX/XLSX/SRT/TXT

**Files:**
- Create: `app/export.py`

**Interfaces:**
- Consumes: `segment.Sentence`
- Produces:
  - `speaker_name(idx: int | None, names: dict | None) -> str` — `names` map key CHUỖI `"0" -> "Anh Huy"`; mặc định `"Người nói {idx+1}"`; trả `""` nếu idx là None
  - `to_docx(sentences, out_path, title, names=None, meta=None) -> Path`
  - `to_xlsx(sentences, out_path, names=None) -> Path`
  - `to_srt(sentences, out_path, names=None) -> Path` (giờ dạng `HH:MM:SS,mmm`)
  - `to_txt(sentences, out_path, names=None) -> Path`
  - Cột "Người nói" tự ẩn nếu mọi `speaker` đều None

- [ ] **Step 1: Viết `app/export.py`**

```python
"""Xuất kết quả: DOCX (bảng subtitle), XLSX, SRT, TXT."""
from pathlib import Path
from typing import Optional

from .segment import Sentence


def _fmt_time(seconds: float, srt: bool = False) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def speaker_name(idx: Optional[int], names: Optional[dict] = None) -> str:
    if idx is None:
        return ""
    if names and str(idx) in names and names[str(idx)].strip():
        return names[str(idx)].strip()
    return f"Người nói {idx + 1}"


def to_docx(sentences: list[Sentence], out_path: Path, title: str,
            names: Optional[dict] = None, meta: Optional[dict] = None) -> Path:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading(title, level=1)
    if meta:
        p = doc.add_paragraph()
        run = p.add_run(" · ".join(f"{k}: {v}" for k, v in meta.items()))
        run.font.size = Pt(9)

    has_speaker = any(s.speaker is not None for s in sentences)
    headers = ["#", "Thời gian"] + (["Người nói"] if has_speaker else []) + ["Nội dung"]
    table = doc.add_table(rows=1, cols=len(headers))
    # Style có thể thiếu trên một số bản python-docx / locale — không được làm hỏng export.
    try:
        table.style = "Light Grid Accent 1"
    except (KeyError, ValueError):
        pass
    for cell, h in zip(table.rows[0].cells, headers):
        cell.text = h
        if cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].bold = True

    for i, s in enumerate(sentences, 1):
        row = table.add_row().cells
        row[0].text = str(i)
        row[1].text = f"{_fmt_time(s.start)} – {_fmt_time(s.end)}"
        if has_speaker:
            row[2].text = speaker_name(s.speaker, names)
        row[-1].text = s.text

    doc.save(str(out_path))
    return out_path


def to_xlsx(sentences: list[Sentence], out_path: Path,
            names: Optional[dict] = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Transcript"
    has_speaker = any(s.speaker is not None for s in sentences)
    headers = ["#", "Bắt đầu", "Kết thúc"] + (["Người nói"] if has_speaker else []) + ["Nội dung"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)

    for i, s in enumerate(sentences, 1):
        row = [i, _fmt_time(s.start), _fmt_time(s.end)]
        if has_speaker:
            row.append(speaker_name(s.speaker, names))
        row.append(s.text)
        ws.append(row)

    widths = [6, 11, 11] + ([16] if has_speaker else []) + [90]
    for col, w in zip("ABCDE", widths):
        ws.column_dimensions[col].width = w
    wrap = Alignment(wrap_text=True, vertical="top")
    for row in ws.iter_rows(min_row=2):
        row[-1].alignment = wrap
    ws.freeze_panes = "A2"
    wb.save(str(out_path))
    return out_path


def to_srt(sentences: list[Sentence], out_path: Path,
           names: Optional[dict] = None) -> Path:
    lines = []
    for i, s in enumerate(sentences, 1):
        who = speaker_name(s.speaker, names)
        text = f"{who}: {s.text}" if who else s.text
        lines.append(
            f"{i}\n{_fmt_time(s.start, srt=True)} --> {_fmt_time(s.end, srt=True)}\n{text}\n"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def to_txt(sentences: list[Sentence], out_path: Path,
           names: Optional[dict] = None) -> Path:
    lines = []
    for s in sentences:
        who = speaker_name(s.speaker, names)
        prefix = f"[{_fmt_time(s.start)}] " + (f"{who}: " if who else "")
        lines.append(prefix + s.text)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
```

- [ ] **Step 2: Verify** — unit test Task 8 (`test_exports_create_files`).
- [ ] **Step 3: Commit** — `git commit -m "feat: export docx/xlsx/srt/txt"`

### Task 7b: Pipeline tổng

**Files:**
- Create: `app/pipeline.py`

**Interfaces:**
- Consumes: tất cả module Task 1–7 (`transcribe.load_model` đã cache 1 model/process — pipeline không tự load trùng trong cùng process)
- Produces:
  - `run(input_path, work_dir, model_key, language="vi", enable_diarization=True, num_speakers=0, glossary_text="", progress=None) -> dict`
  - dict kết quả: `{sentences: [asdict(Sentence)], duration: float, num_speakers: int, extracted_audio: str|None, model: str}`
  - `progress(stage: str, percent: float, message: str)`; stage ∈ convert/model/transcribe/diarize/finalize/done; thang %: 2→6→12–70→72–92→94→100

- [ ] **Step 1: Viết `app/pipeline.py`**

```python
"""Ghép toàn bộ pipeline: convert → transcribe → diarize → sửa glossary → tách câu."""
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from . import config, diarize, glossary, media, segment, transcribe

ProgressCb = Callable[[str, float, str], None]  # (stage, percent 0-100, message)


def run(
    input_path: Path,
    work_dir: Path,
    model_key: str,
    language: str = "vi",
    enable_diarization: bool = True,
    num_speakers: int = 0,
    glossary_text: str = "",
    progress: Optional[ProgressCb] = None,
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

    # 3. Transcribe (chiếm phần lớn thời gian)
    report("transcribe", 12, "Đang chuyển giọng nói thành văn bản…")
    settings = config.load_settings()
    words = transcribe.transcribe(
        model, wav, duration,
        language=language,
        beam_size=int(settings.get("beam_size", 5)),
        hotwords=gloss.hotwords or None,
        progress_cb=lambda f: report(
            "transcribe", 12 + f * 58, f"Đang chuyển giọng nói thành văn bản… {int(f * 100)}%"
        ),
    )

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
    }
```

- [ ] **Step 2: Verify** — `uv run python -c "import app.pipeline; print('ok')"` (chạy thật ở Task 12).
- [ ] **Step 3: Commit** — `git commit -m "feat: pipeline tong"`

### Task 8: Unit tests cho core

**Files:**
- Create: `tests/__init__.py` (rỗng), `tests/test_core.py`

**Interfaces:** Consumes interface Task 1, 5, 6, 7.

- [ ] **Step 1: Viết `tests/test_core.py`**

```python
import tempfile
from pathlib import Path

from app.diarize import SpeakerTurn
from app.export import to_docx, to_srt, to_txt, to_xlsx
from app.glossary import correct, parse
from app.segment import Sentence, assign_speakers, build_sentences
from app.transcribe import Word


def _words(spec):
    # spec: [(start, end, " text"), ...] — text có khoảng trắng đầu như Whisper trả về
    return [Word(s, e, t) for s, e, t in spec]


def test_build_sentences_breaks_on_punctuation():
    words = _words(
        [(0.0, 0.5, " Xin"), (0.5, 1.0, " chào."), (1.1, 1.6, " Tôi"), (1.6, 2.2, " là Huy.")]
    )
    sents = build_sentences(words)
    assert [s.text for s in sents] == ["Xin chào.", "Tôi là Huy."]
    assert sents[0].start == 0.0 and sents[0].end == 1.0


def test_build_sentences_breaks_on_gap():
    words = _words([(0.0, 0.5, " một"), (5.0, 5.5, " hai")])  # gap 4.5s > 1.2s
    assert len(build_sentences(words)) == 2


def test_assign_speakers_by_overlap():
    sents = [Sentence(0.0, 2.0, "a"), Sentence(2.5, 4.0, "b"), Sentence(9.0, 9.5, "c")]
    turns = [SpeakerTurn(0.0, 2.2, 0), SpeakerTurn(2.3, 5.0, 1)]
    assign_speakers(sents, turns)
    assert [s.speaker for s in sents] == [0, 1, 1]  # câu c không overlap → theo câu trước


def test_glossary_exact_replacement_vietnamese_boundary():
    g = parse("nờ vi đi a => NVIDIA\n# comment\nVinamilk")
    assert g.hotwords == "NVIDIA, Vinamilk"
    assert correct("hãng nờ vi đi a ra chip mới", g) == "hãng NVIDIA ra chip mới"


def test_glossary_fuzzy_snap():
    g = parse("Vinamilk")
    assert correct("cổ phiếu Vinamik tăng", g) == "cổ phiếu Vinamilk tăng"


def test_glossary_no_false_positive():
    g = parse("Vinamilk")
    text = "vina cà phê rất ngon"
    assert correct(text, g) == text


def test_exports_create_files():
    sents = [Sentence(0.0, 2.0, "Xin chào.", 0), Sentence(2.0, 4.0, "Chào bạn.", 1)]
    names = {"0": "Anh Huy"}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        to_docx(sents, d / "a.docx", "Test", names, {"Model": "x"})
        to_xlsx(sents, d / "a.xlsx", names)
        to_srt(sents, d / "a.srt", names)
        to_txt(sents, d / "a.txt", names)
        for f in ["a.docx", "a.xlsx", "a.srt", "a.txt"]:
            assert (d / f).exists() and (d / f).stat().st_size > 0
        srt = (d / "a.srt").read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:02,000" in srt
        assert "Anh Huy: Xin chào." in srt
        assert "Người nói 2: Chào bạn." in srt


def test_settings_roundtrip(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    s = config.save_settings({"model": "phowhisper-medium", "bogus": 1})
    assert s["model"] == "phowhisper-medium"
    assert "bogus" not in s
    assert config.load_settings()["model"] == "phowhisper-medium"
```

- [ ] **Step 2: Chạy** — Run: `uv run pytest tests/ -v`. Expected: 8 passed. Đây là lần verify logic đầu tiên của Task 1, 5, 6, 7 — sửa code core nếu fail.
- [ ] **Step 3: Lint** — `uv run ruff check .` sạch.
- [ ] **Step 4: Commit** — `git commit -m "test: unit tests core"`

### Task 9: Web server (FastAPI + job manager)

**Files:**
- Create: `app/server.py`

**Interfaces:**
- Consumes: `pipeline.run`, `config.*`, `export.*`, `media.is_supported`, `segment.Sentence`
- Produces (HTTP API cho Task 10):
  - `GET /` → index.html
  - `GET /api/meta` → `{models: [{key,label,size,downloaded}], settings, glossary}`
  - `POST /api/jobs` (multipart: `file`, `model`, `language`, `diarize`, `num_speakers`, `glossary`) → `{job_id}`; đồng thời lưu model+glossary làm mặc định
  - **v1 chỉ 1 job chạy tại một thời điểm** — nếu đã có job `status=running` thì `POST /api/jobs` trả **HTTP 409** (tránh load 2 model song song trên máy CPU yếu)
  - `GET /api/jobs/{id}` → `{status: running|done|error, stage, percent, message, filename, result?}`
  - `POST /api/jobs/{id}/export` (JSON `{format: docx|xlsx|srt|txt, names: {"0": "Tên"}}`) → file download; `Content-Disposition` dùng stem file gốc (`{stem}.{fmt}`), không hard-code `transcript.*`
  - `GET /api/jobs/{id}/audio` → file audio đã tách (chỉ khi input là video)
  - Form `diarize`: gửi chuỗi `"true"`/`"false"` từ JS; FastAPI parse bool form đúng — verify uncheck → `enable_diarization=False` ở Task 12
- `python -m app.server` → chọn port trống từ 8756, mở browser sau 1.5s, uvicorn host 127.0.0.1

- [ ] **Step 1: Viết `app/server.py`**

```python
"""Web server local: FastAPI + job chạy nền trong thread. Chạy: python -m app.server"""
import socket
import threading
import uuid
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import config, export, media, pipeline
from .segment import Sentence

app = FastAPI(title="ViTranscript")
JOBS: dict[str, dict] = {}
_STATIC = Path(__file__).parent / "static"
_EXPORTERS = {"docx": export.to_docx, "xlsx": export.to_xlsx,
              "srt": export.to_srt, "txt": export.to_txt}


def _any_job_running() -> bool:
    return any(j.get("status") == "running" for j in JOBS.values())


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def meta():
    return {
        "models": [
            {"key": k, "label": v["label"], "size": v["size"],
             "downloaded": config.model_is_downloaded(k)}
            for k, v in config.MODEL_REGISTRY.items()
        ],
        "settings": config.load_settings(),
        "glossary": config.load_glossary_text(),
    }


def _run_job(job_id: str, input_path: Path, opts: dict) -> None:
    job = JOBS[job_id]

    def progress(stage: str, pct: float, msg: str):
        job.update(stage=stage, percent=round(pct, 1), message=msg)

    try:
        result = pipeline.run(
            input_path, input_path.parent, opts["model"],
            language=opts["language"], enable_diarization=opts["diarize"],
            num_speakers=opts["num_speakers"], glossary_text=opts["glossary"],
            progress=progress,
        )
        job.update(status="done", result=result, percent=100)
    except Exception as e:  # hiển thị lỗi cho người dùng thay vì treo job
        job.update(status="error", message=f"Lỗi: {e}", percent=100)


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    model: str = Form(...),
    language: str = Form("vi"),
    diarize: bool = Form(True),
    num_speakers: int = Form(0),
    glossary: str = Form(""),
):
    # v1: tuần tự 1 job — máy CPU-only không chịu được 2 WhisperModel cùng lúc
    if _any_job_running():
        raise HTTPException(
            409,
            "Đang có job khác chạy. Vui lòng đợi xong rồi thử lại.",
        )
    if model not in config.MODEL_REGISTRY:
        raise HTTPException(400, "Model không hợp lệ")
    name = Path(file.filename or "input")
    if not media.is_supported(name):
        raise HTTPException(400, f"Định dạng {name.suffix} chưa hỗ trợ")

    job_id = uuid.uuid4().hex[:12]
    job_dir = config.jobs_dir() / job_id
    job_dir.mkdir(parents=True)
    input_path = job_dir / ("input" + name.suffix.lower())
    with input_path.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    config.save_settings({"model": model, "language": language})
    config.save_glossary_text(glossary)

    JOBS[job_id] = {"status": "running", "stage": "queued", "percent": 0,
                    "message": "Đang chuẩn bị…", "filename": name.name}
    opts = {"model": model, "language": language, "diarize": diarize,
            "num_speakers": num_speakers, "glossary": glossary}
    threading.Thread(target=_run_job, args=(job_id, input_path, opts), daemon=True).start()
    return {"job_id": job_id}


def _get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "Không tìm thấy job")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _get_job(job_id)


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, body: dict):
    job = _get_job(job_id)
    if job.get("status") != "done":
        raise HTTPException(409, "Job chưa xong")
    fmt = body.get("format", "docx")
    if fmt not in _EXPORTERS:
        raise HTTPException(400, "Định dạng không hợp lệ")
    names = body.get("names") or {}
    sentences = [Sentence(**s) for s in job["result"]["sentences"]]
    stem = Path(job["filename"]).stem
    out = config.jobs_dir() / job_id / f"{stem}.{fmt}"
    if fmt == "docx":
        export.to_docx(sentences, out, f"Transcript — {job['filename']}", names,
                       {"Model": job["result"]["model"],
                        "Thời lượng": f"{job['result']['duration']:.0f}s"})
    else:
        _EXPORTERS[fmt](sentences, out, names)
    return FileResponse(out, filename=out.name)


@app.get("/api/jobs/{job_id}/audio")
def download_audio(job_id: str):
    job = _get_job(job_id)
    extracted = (job.get("result") or {}).get("extracted_audio")
    if not extracted or not Path(extracted).exists():
        raise HTTPException(404, "Không có file audio tách riêng (đầu vào không phải video)")
    p = Path(extracted)
    return FileResponse(p, filename=Path(job["filename"]).stem + p.suffix)


def _free_port(start: int = 8756) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Không tìm được port trống")


def main() -> None:
    port = _free_port()
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"\n  ViTranscript đang chạy tại http://127.0.0.1:{port}  (Ctrl+C để thoát)\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify API bằng curl** (tạm `mkdir -p app/static && echo ok > app/static/index.html` nếu Task 10 chưa làm)

Run: `uv run python -m app.server &`, rồi `curl -s http://127.0.0.1:8756/api/meta | python3 -m json.tool`
Expected: JSON có 5 model, `settings.model = "phowhisper-small"`.

- [ ] **Step 3: Lint + Commit** — `uv run ruff check .` → `git commit -m "feat: web server fastapi"`

### Task 10: Giao diện web (1 trang HTML tiếng Việt)

**Files:**
- Create: `app/static/index.html`

**Interfaces:** Consumes toàn bộ HTTP API Task 9.

**Spec hành vi (bắt buộc đủ 6 mục):**
1. Khu chọn file: input file + drag-drop, hiện tên file đã chọn; `accept` đúng danh sách đuôi `AUDIO_EXTS | VIDEO_EXTS` của `media.py`.
2. Khu tùy chọn: select model (label + size, đánh dấu "✓ đã tải" theo `downloaded`, chọn sẵn `settings.model`), select ngôn ngữ (Tiếng Việt `vi` / Tự nhận diện `auto`), checkbox "Phân biệt người nói" (mặc định bật), input số người nói (0 = tự đoán), textarea glossary (prefill từ `/api/meta`, placeholder hướng dẫn cú pháp `sai => đúng` và từ khóa mỗi dòng).
3. Nút "Bắt đầu transcript" → POST FormData; disable khi đang chạy.
4. Tiến trình: progress bar % + message; poll `GET /api/jobs/{id}` mỗi 1.2s; lỗi hiện chữ đỏ nếu `status=error`.
5. Kết quả: (a) ô đổi tên cho từng speaker xuất hiện trong kết quả (placeholder "Người nói N"), gõ tên cập nhật preview ngay; (b) bảng preview tối đa 300 câu (thời gian — người nói — nội dung); (c) 4 nút tải DOCX/XLSX/SRT/TXT gọi POST export với `{format, names}`, nhận blob, tải xuống tên `transcript.<fmt>`; (d) nút "Tải audio đã tách" chỉ hiện khi `result.extracted_audio` khác null.
6. Giao diện: CSS thuần nội tuyến, font `system-ui`, một cột tối đa 860px, không tải tài nguyên ngoài (offline hoàn toàn).

- [ ] **Step 1: Viết `app/static/index.html`** theo spec; khung JS chính:

```html
<script>
let jobId = null, result = null, names = {};
async function loadMeta() { /* fetch /api/meta → render select model, prefill glossary */ }
async function start() {
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("model", modelSel.value);
  fd.append("language", langSel.value);
  fd.append("diarize", diarizeChk.checked);
  fd.append("num_speakers", numSpeakers.value || 0);
  fd.append("glossary", glossaryTa.value);
  const r = await fetch("/api/jobs", {method: "POST", body: fd});
  if (!r.ok) return showError((await r.json()).detail);
  jobId = (await r.json()).job_id;
  poll();
}
async function poll() {
  const j = await (await fetch(`/api/jobs/${jobId}`)).json();
  renderProgress(j);
  if (j.status === "running") return setTimeout(poll, 1200);
  if (j.status === "done") { result = j.result; renderResult(); }
  else showError(j.message);
}
async function download(fmt) {
  // Tên file: ưu tiên Content-Disposition từ server (stem gốc); fallback transcript.<fmt>
  const r = await fetch(`/api/jobs/${jobId}/export`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({format: fmt, names})});
  const blob = await r.blob();
  const cd = r.headers.get("content-disposition") || "";
  const m = /filename="?([^";]+)"?/i.exec(cd);
  const filename = m ? m[1] : `transcript.${fmt}`;
  const a = Object.assign(document.createElement("a"),
    {href: URL.createObjectURL(blob), download: filename});
  a.click(); URL.revokeObjectURL(a.href);
}
</script>
```

- [ ] **Step 2: Verify thủ công — checklist QA (PASS/FAIL từng dòng)**

| # | Hành vi | Cách kiểm | Expected |
|---|---|---|---|
| 1a | Chọn file bằng input | Click chọn `.mp3` | Hiện tên file đã chọn |
| 1b | Drag-drop | Kéo file vào vùng drop | Tên file cập nhật; file không hỗ trợ → báo lỗi rõ |
| 1c | `accept` | Xem attribute input | Khớp đuôi audio+video của `media.py` |
| 2a | Model list | Mở select | Đủ 5 model; label + size; model đã tải có "✓ đã tải"; preselect `settings.model` |
| 2b | Ngôn ngữ | Đổi select | Có `vi` và `auto` |
| 2c | Diarization | Bỏ tick checkbox rồi start (smoke) | Job chạy với diarize=false (không stage diarize, hoặc `num_speakers=0` trong result) |
| 2d | Glossary | Xem textarea | Prefill từ meta; placeholder có `sai => đúng` |
| 3 | Start + disable | Bấm "Bắt đầu" khi đang chạy | Nút disable; không gửi job thứ 2 (server 409 nếu cố) |
| 4a | Progress | Trong lúc job running | Bar % + message tiếng Việt; poll ~1.2s |
| 4b | Error | (tùy chọn) file hỏng | `status=error` → chữ đỏ + message |
| 5a | Đổi tên speaker | Gõ tên vào ô speaker | Preview bảng cập nhật ngay |
| 5b | Preview cap | (file dài) | Tối đa 300 câu trong bảng |
| 5c | Export 4 định dạng | Lần lượt DOCX/XLSX/SRT/TXT | Tải được file; tên theo stem gốc (hoặc fallback `transcript.*`) |
| 5d | Audio tách | Job từ video | Nút "Tải audio đã tách" hiện; job audio thuần → ẩn |
| 6 | Offline UI | DevTools → Network: no CDN | Chỉ request localhost; font system-ui; layout ≤860px |

Job thật end-to-end gộp Task 12; Task 10 tối thiểu: load UI + meta + checklist 1–2, 6 không cần model.

- [ ] **Step 3: Commit** — `git commit -m "feat: giao dien web tieng viet"`

### Task 11: Script cài đặt & chạy 1-click

**Files:**
- Create: `install.command`, `run.command` (Mac, `chmod +x`), `install.bat`, `run.bat` (Windows)

**Interfaces:** Consumes `pyproject.toml` + `.python-version`; Produces trải nghiệm cài đặt người dùng cuối.

- [ ] **Step 1: Viết 4 script**

`install.command`:
```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== Cài đặt ViTranscript ==="
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "Đang cài công cụ uv (tự quản lý Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv sync
echo
echo "✅ Cài đặt hoàn tất! Mở ứng dụng bằng cách nhấp đúp file run.command"
read -n 1 -s -r -p "Nhấn phím bất kỳ để đóng…"
```

`run.command`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
uv run python -m app.server
```

`install.bat`:
```bat
@echo off
cd /d "%~dp0"
echo === Cai dat ViTranscript ===
where uv >nul 2>nul
if errorlevel 1 (
  echo Dang cai cong cu uv...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
uv python install 3.12
uv sync
echo.
echo Cai dat hoan tat! Mo ung dung bang file run.bat
pause
```

`run.bat`:
```bat
@echo off
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
uv run python -m app.server
```

- [ ] **Step 2:** `chmod +x install.command run.command`
- [ ] **Step 3: Verify trên máy dev** — `./install.command` rồi `./run.command`. Expected: browser mở UI. (Windows verify khi có máy thật — ghi vào 03-tasks.md.)
- [ ] **Step 4: Commit** — `git commit -m "chore: script cai dat 1-click"`

### Task 12: Smoke test end-to-end + sửa lỗi phát sinh

**Files:**
- Create: `scripts/smoke_e2e.py`

**Interfaces:** Consumes `pipeline.run`, `export.*`. Đây là lần đầu toàn pipeline chạy thật → dự kiến phải sửa lỗi nhỏ ở Task 2–7b (API sherpa-onnx/faster-whisper lệch phiên bản; API `static_ffmpeg` nếu khác bản).

**Phạm vi nền tảng:**
- Script dưới đây **macOS-only** (dùng lệnh `say` tạo 2 giọng). Đây là smoke mặc định trên máy dev Mac.
- **Windows:** không chạy `smoke_e2e.py` như viết; nghiệm thu bằng UI + file audio thật (Task 14) và unit tests. (Tuỳ chọn sau v0.1: sinh WAV tone bằng numpy/ffmpeg thuần, không `say`.)
- Cũng verify: (1) uncheck diarization → không chạy stage diarize; (2) start job thứ 2 khi job 1 running → HTTP 409.

- [ ] **Step 1: Viết `scripts/smoke_e2e.py`**

```python
"""Smoke test end-to-end trên máy dev (macOS): sinh audio 2 giọng bằng `say`,
chạy pipeline với model tiny, in kết quả. Chạy: uv run python scripts/smoke_e2e.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import config, export, pipeline
from app.segment import Sentence

# đăng ký model tiny (75MB) chỉ cho smoke test
config.MODEL_REGISTRY["tiny-test"] = {"source": "tiny", "label": "test", "size": "75MB"}

work = Path(tempfile.mkdtemp(prefix="vitranscript_smoke_"))
part_a, part_b = work / "a.aiff", work / "b.aiff"
subprocess.run(["say", "-v", "Linh", "-o", part_a,
                "Xin chào các bạn. Hôm nay chúng ta họp về dự án Vinamilk."], check=True)
subprocess.run(["say", "-v", "Samantha", "-o", part_b,
                "OK let me check the report."], check=True)
merged = work / "merged.m4a"
subprocess.run(["ffmpeg", "-y", "-i", part_a, "-i", part_b, "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1", merged], check=True, capture_output=True)

result = pipeline.run(
    merged, work / "job", "tiny-test", language="auto",
    enable_diarization=True, num_speakers=2,
    glossary_text="vina milk => Vinamilk\nVinamilk",
    progress=lambda st, p, m: print(f"  [{st} {p:.0f}%] {m}"),
)
sents = [Sentence(**s) for s in result["sentences"]]
for s in sents:
    print(f"{s.start:6.1f}–{s.end:6.1f}  SPK{s.speaker}  {s.text}")
export.to_docx(sents, work / "out.docx", "Smoke", None, None)
export.to_xlsx(sents, work / "out.xlsx", None)
assert (work / "out.docx").exists() and (work / "out.xlsx").exists()
print(f"\n✅ Smoke test OK — kết quả tại {work}")
```

- [ ] **Step 2: Chạy** — Run: `uv run python scripts/smoke_e2e.py`. Expected: in tiến trình từng stage, ≥2 câu, 2 speaker khác nhau, tạo được docx/xlsx. Sửa mọi lỗi API cho đến khi pass.
- [ ] **Step 3: Chạy lại unit tests + lint** — `uv run pytest tests/ -v` (8 passed) và `uv run ruff check .` sạch.
- [ ] **Step 4: Test qua UI thật** — mở app, nạp chính file `merged.m4a`, chạy model mặc định PhoWhisper-small (tải ~490MB lần đầu), đổi tên speaker, tải đủ 4 định dạng.
- [ ] **Step 5: Commit** — `git commit -m "test: smoke e2e + sua loi phat sinh"`

### Task 12b: Golden file — đo chất lượng transcript (WER)

**Files:**
- Create: `scripts/eval_wer.py`, `eval/README.md`
- (Người dùng cung cấp: `eval/sample.<đuôi audio/video>` + `eval/sample.txt` transcript gõ tay)

**Interfaces:** Consumes `pipeline.run`. Produces: con số WER làm mốc khách quan khi đổi model/tham số (thay cho cảm tính "nghe có vẻ đúng").

- [ ] **Step 1: Viết `eval/README.md`** — hướng dẫn: đặt file hội thoại thật 3–5 phút tên `sample.*` + transcript gõ tay `sample.txt` (đúng chính tả, không cần timestamp) vào thư mục này; file này KHÔNG commit (thêm `eval/sample.*` vào `.gitignore` — dữ liệu cá nhân).

- [ ] **Step 2: Viết `scripts/eval_wer.py`**

```python
"""Đo tỷ lệ lỗi từ (WER) của pipeline trên audio mẫu thật.

Chuẩn bị theo eval/README.md. Chạy: uv run python scripts/eval_wer.py [model_key]
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from jiwer import wer

from app import config, pipeline

EVAL = Path(__file__).parent.parent / "eval"


def normalize(t: str) -> str:
    t = re.sub(r"[^\wÀ-ỹ ]", " ", t.lower())
    return " ".join(t.split())


ref_path = EVAL / "sample.txt"
audio = next((p for p in EVAL.glob("sample.*") if p.suffix != ".txt"), None)
if not audio or not ref_path.exists():
    sys.exit("Thiếu eval/sample.<audio> hoặc eval/sample.txt — xem eval/README.md")

model_key = sys.argv[1] if len(sys.argv) > 1 else config.load_settings()["model"]
work = Path(tempfile.mkdtemp(prefix="vitranscript_eval_"))
result = pipeline.run(audio, work, model_key, enable_diarization=False,
                      progress=lambda st, p, m: print(f"  [{st} {p:.0f}%] {m}"))
hyp = " ".join(s["text"] for s in result["sentences"])
score = wer(normalize(ref_path.read_text(encoding="utf-8")), normalize(hyp))
print(f"\nModel: {model_key}\nWER: {score:.1%}")
print("Mốc tham khảo: <15% tốt · 15–30% chấp nhận được · >30% xem lại model/chất lượng ghi âm")
```

- [ ] **Step 3: Chạy với ≥2 model** — Run: `uv run python scripts/eval_wer.py phowhisper-small` và `uv run python scripts/eval_wer.py large-v3-turbo`. Ghi kết quả vào bảng trong [03-tasks.md](03-tasks.md) để chốt model mặc định bằng số liệu.
- [ ] **Step 4: Commit** — `git commit -m "feat: eval WER golden file"` (không commit file sample)

### Task 13: README người dùng cuối

**Files:**
- Create: `README.md`

- [ ] **Step 1: Viết README.md tiếng Việt** gồm đúng các mục:
  1. Giới thiệu 3 dòng + cam kết riêng tư (mọi thứ chạy trên máy, không gửi dữ liệu đi đâu)
  2. Cài đặt Mac (double-click `install.command`; nếu macOS chặn: chuột phải → Open) / Windows (double-click `install.bat`)
  3. Cách dùng: chạy `run`, chọn file, tùy chọn, bấm nút, đổi tên người nói, tải kết quả; **lưu ý v1 chỉ chạy 1 job tại một thời điểm**
  4. Glossary: cú pháp `sai => đúng`, từ khóa đơn; ví dụ cụ thể
  5. Chọn model nào: bảng 5 model (tốc độ/độ chính xác/dung lượng, khuyến nghị theo máy; điền số WER đo được ở Task 12b)
  6. Giới hạn cần biết: diarization phụ thuộc chất lượng ghi âm; lần đầu cần mạng tải model, sau đó offline; model lớn tốn RAM
  7. Troubleshooting (ghi **đường dẫn data chính xác**):
     - **macOS:** `~/Library/Application Support/ViTranscript` (model, settings, glossary, jobs)
     - **Windows:** `%APPDATA%\ViTranscript` (thường `C:\Users\<tên>\AppData\Roaming\ViTranscript`)
     - **Linux (nếu chạy):** `~/.local/share/ViTranscript` hoặc `$XDG_DATA_HOME/ViTranscript`
     - Xóa cả thư mục trên = reset app (tải lại model lần sau)
     - Port bận, macOS Gatekeeper, ffmpeg thiếu (app tự fallback static-ffmpeg)
     - Windows: nếu `uv` không tìm thấy sau install, mở lại CMD hoặc thêm `%USERPROFILE%\.local\bin` vào PATH
- [ ] **Step 2: Verify** — đọc lại theo vai người không biết kỹ thuật; mọi bước đều là double-click hoặc copy-paste 1 lệnh.
- [ ] **Step 3: Commit** — `git commit -m "docs: README nguoi dung cuoi"`

### Task 14: Nghiệm thu theo tiêu chí bài toán

- [ ] Chạy checklist mục 8 của [01-bai-toan.md](01-bai-toan.md) (tiêu chí 1–6), ghi PASS/FAIL vào [03-tasks.md](03-tasks.md)
- [ ] Tiêu chí offline: tắt Wi-Fi, chạy lại 1 job với model đã tải. Expected: hoàn tất bình thường.
- [ ] Commit cuối: `git commit -m "docs: ket qua nghiem thu"` + gắn tag `git tag v0.1.0`

---

## Self-review (đã chạy khi lập plan)

- **Coverage:** 5 yêu cầu gốc → convert (Task 2), transcript + đổi model (Task 3, 9, 10), export docx/xlsx (Task 7, 9, 10), glossary (Task 5, 9, 10), tách câu + diarization (Task 4, 6). Chất lượng đo được: Task 12b. Đủ.
- **Placeholder:** Task 10 Step 1 có khung JS + spec 6 mục thay vì HTML đầy đủ — bù bằng **checklist QA PASS/FAIL** (Step 2) đủ nghiệm thu hành vi; markup/CSS không có quyết định kiến trúc.
- **Type consistency:** `names` dùng key kiểu chuỗi (`"0"`) xuyên suốt export/server/UI; `Sentence(**dict)` khớp `asdict` của pipeline; `Word`/`SpeakerTurn`/`Sentence` cùng đơn vị giây (float). Download filename: server stem gốc; UI đọc `Content-Disposition`. Đã soát.
- **Lưu ý phiên bản:** API `sherpa_onnx.OfflineSpeakerDiarization` và tham số `hotwords` của faster-whisper viết theo hiểu biết đến 01/2026 — Task 12 là chốt chặn bắt lệch API (đã ghi phương án fallback trong Task 3).
- **Plan review 2026-07-17 (P0/P1 đã vá vào plan):**
  1. `numpy` khai báo tường minh (Task 0)
  2. Cache 1 WhisperModel / process (Task 3 `load_model`)
  3. Server từ chối job song song HTTP 409 (Task 9) — khớp brief “v1 tuần tự”
  4. DOCX table style try/except (Task 7)
  5. Task 10 checklist QA chi tiết; Task 12 ghi macOS-only smoke
  6. Task 13 đường dẫn data đầy đủ 3 OS
  - **Còn mở (không chặn code):** Windows verify installer trên máy thật; golden file WER do người dùng cung cấp; GC job disk (xóa data thủ công qua README).
