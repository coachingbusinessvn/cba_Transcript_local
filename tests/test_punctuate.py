import hashlib
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


def test_ensure_model_dir_verifies_hash_and_writes_manifest(monkeypatch, tmp_path):
    from app import config, punctuate

    payload = b"verified-model"
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", len(payload))
    monkeypatch.setitem(
        config.PUNCTUATION_MODEL, "sha256", hashlib.sha256(payload).hexdigest()
    )

    def fake_snapshot_download(**kwargs):
        root = config.punctuation_dir()
        (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(payload)
        (root / "vocab.txt").write_text("[PAD]\n[UNK]\n", encoding="utf-8")
        labels = root / "vocabulary" / "labels.txt"
        labels.parent.mkdir(parents=True)
        labels.write_text("$KEEP\n", encoding="utf-8")
        (root / "config.json").write_text("{}", encoding="utf-8")
        (root / "README.md").write_text("license", encoding="utf-8")
        return str(root)

    monkeypatch.setattr(punctuate, "_snapshot_download", fake_snapshot_download)
    root = punctuate._ensure_model_dir()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == config.PUNCTUATION_MODEL["revision"]
    assert manifest["sha256"] == config.PUNCTUATION_MODEL["sha256"]


def test_ensure_model_dir_rejects_wrong_hash(monkeypatch, tmp_path):
    import pytest

    from app import config, punctuate

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", 3)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "sha256", "0" * 64)

    def fake_snapshot_download(**kwargs):
        root = config.punctuation_dir()
        (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(b"bad")
        return str(root)

    monkeypatch.setattr(punctuate, "_snapshot_download", fake_snapshot_download)
    with pytest.raises(RuntimeError, match="SHA-256"):
        punctuate._ensure_model_dir()
    assert not config.punctuation_manifest_path().exists()


def test_runtime_is_cached_once(monkeypatch, tmp_path):
    from app import punctuate

    calls = []
    monkeypatch.setattr(punctuate, "_RUNTIME_CACHE", None)
    monkeypatch.setattr(punctuate, "_ensure_model_dir", lambda: tmp_path)
    monkeypatch.setattr(
        punctuate, "_create_runtime", lambda root: calls.append(root) or object()
    )
    assert punctuate._load_runtime() is punctuate._load_runtime()
    assert calls == [tmp_path]


def test_case_actions_are_exact_and_unsupported_actions_keep_text():
    from app.punctuate import _apply_case

    assert _apply_case("hà", "$TRANSFORM_CASE_CAPITAL") == "Hà"
    assert _apply_case("who", "$TRANSFORM_CASE_UPPER") == "WHO"
    assert _apply_case("VN", "$TRANSFORM_CASE_LOWER") == "vn"
    assert _apply_case("iphone", "$TRANSFORM_CASE_CAPITAL_1") == "iPhone"
    assert _apply_case("iphone", "$TRANSFORM_CASE_UPPER_-1") == "IPHONe"
    assert _apply_case("nguyên", "$TRANSFORM_VERB_VB_VBN") == "nguyên"
    assert _apply_case("nguyên", "$MERGE_SPACE") == "nguyên"


def test_chunk_ranges_have_48_words_and_12_overlap():
    from app.punctuate import _chunk_ranges

    assert _chunk_ranges(100) == [(0, 48), (36, 84), (72, 100)]
    assert _chunk_ranges(2) == [(0, 2)]
