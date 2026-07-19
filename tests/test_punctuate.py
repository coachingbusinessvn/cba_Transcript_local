import json


def test_punctuation_model_is_pinned():
    from app.config import PUNCTUATION_MODEL

    assert PUNCTUATION_MODEL == {
        "repo_id": "welcomyou/vibert-capu-onnx",
        "revision": "a7754d037f4a9e29f7f3224f27acb60149eab874",
        "filename": "vibert-capu.int8.onnx",
        "size": 115_707_731,
        "sha256": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
        "license": "CC-BY-SA-4.0",
    }


def test_punctuation_cache_requires_matching_manifest(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = config.punctuation_dir()
    model = root / config.PUNCTUATION_MODEL["filename"]
    model.write_bytes(b"abc")
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", 3)
    assert config.punctuation_is_downloaded() is False

    (root / "manifest.json").write_text(
        json.dumps({
            "revision": config.PUNCTUATION_MODEL["revision"],
            "sha256": config.PUNCTUATION_MODEL["sha256"],
        }),
        encoding="utf-8",
    )
    assert config.punctuation_is_downloaded() is True


def test_punctuate_setting_defaults_true_and_rejects_non_bool(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert config.load_settings()["punctuate"] is True
    assert config.save_settings({"punctuate": False})["punctuate"] is False
    assert config.save_settings({"punctuate": "false"})["punctuate"] is False
