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
