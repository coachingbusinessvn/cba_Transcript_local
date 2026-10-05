"""Cấu hình chung: đường dẫn dữ liệu, danh sách model, settings người dùng."""
import hashlib
import json
import os
import sys
from pathlib import Path

APP_NAME = "ViTranscript"

# Danh sách model transcript. Tất cả đều ở định dạng CTranslate2, chạy trên
# faster-whisper, CPU int8 — không cần GPU, không cần tài khoản Hugging Face.
# "revision" ghim commit Hugging Face: repo bên thứ ba (tài khoản cá nhân) có thể
# bị thay weights/tokenizer bất cứ lúc nào — ghim commit để mọi máy tải đúng
# một bản đã kiểm, kết quả tái lập được. Nâng model = sửa SHA ở đây.
MODEL_REGISTRY = {
    "phowhisper-small": {
        "source": "diepho/PhoWhisper-small-ct2",
        "revision": "5463cb9d0040071dcc245038d1039d7edee45a1c",
        "label": "PhoWhisper Small — nhanh, tiếng Việt tốt (mặc định)",
        "size": "~490 MB",
    },
    "phowhisper-medium": {
        "source": "diepho/PhoWhisper-medium-ct2",
        "revision": "7ab76fc86fdf36847c091c08850ded2daffb66d7",
        "label": "PhoWhisper Medium — chính xác hơn, chậm hơn ~2x",
        "size": "~1.5 GB",
    },
    "phowhisper-large": {
        "source": "kiendt/PhoWhisper-large-ct2",
        "revision": "abceb098c94235c16414dda9e1aada82ebcf6288",
        "label": "PhoWhisper Large — chính xác nhất cho tiếng Việt, chậm",
        "size": "~3 GB",
    },
    "large-v3-turbo": {
        "source": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "revision": "4df90f75321148c3a29a9e2351b7ddf8f5b115a8",
        "label": "Whisper Large-v3 Turbo — tốt khi xen nhiều tiếng Anh",
        "size": "~1.6 GB",
    },
    "whisper-small": {
        "source": "small",
        "revision": "536b0662742c02347bc0e980a01041f333bce120",
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
    """Model coi như đã tải nếu snapshot đúng revision đã ghim có model.bin
    trong cache Hugging Face local (snapshot revision cũ không tính)."""
    entry = MODEL_REGISTRY[model_key]
    source = entry["source"]
    if "/" not in source:  # tên built-in của faster-whisper (vd. "small")
        source = f"Systran/faster-whisper-{source}"
    cache_name = "models--" + source.replace("/", "--")
    return (models_dir() / cache_name / "snapshots" / entry["revision"] / "model.bin").exists()
