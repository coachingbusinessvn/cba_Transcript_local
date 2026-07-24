"""Cấu hình chung: đường dẫn dữ liệu, danh sách model, settings người dùng."""
import hashlib
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

PUNCTUATION_MODEL = {
    "repo_id": "welcomyou/vibert-capu-onnx",
    "revision": "a7754d037f4a9e29f7f3224f27acb60149eab874",
    "filename": "vibert-capu.int8.onnx",
    "size": 115_707_731,
    "sha256": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
    "license": "CC-BY-SA-4.0",
}

DEFAULT_SETTINGS = {
    "model": "phowhisper-small",
    "language": "vi",
    "beam_size": 5,
    "punctuate": True,
}


def sha256_file(path: Path) -> str:
    """SHA-256 của file, đọc theo khối 1 MB (model có thể vài trăm MB)."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


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


def punctuation_dir() -> Path:
    d = data_dir() / "punctuation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def punctuation_manifest_path() -> Path:
    return punctuation_dir() / "manifest.json"


def punctuation_is_downloaded() -> bool:
    model_path = punctuation_dir() / PUNCTUATION_MODEL["filename"]
    try:
        manifest = json.loads(punctuation_manifest_path().read_text(encoding="utf-8"))
        return (
            model_path.is_file()
            and model_path.stat().st_size == PUNCTUATION_MODEL["size"]
            and manifest.get("revision") == PUNCTUATION_MODEL["revision"]
            and manifest.get("sha256") == PUNCTUATION_MODEL["sha256"]
        )
    except (OSError, ValueError):
        return False


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
    updates = {k: v for k, v in new_values.items() if k in DEFAULT_SETTINGS}
    if "punctuate" in updates and not isinstance(updates["punctuate"], bool):
        updates.pop("punctuate")
    s.update(updates)
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
