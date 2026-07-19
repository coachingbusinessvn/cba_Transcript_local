import hashlib
import json

from app.transcribe import Word


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


def _word_tuples(words):
    return [(w.start, w.end, w.text) for w in words]


def test_restore_keeps_count_timestamps_input_and_blocks_word_edits(monkeypatch):
    from app import punctuate

    original = [Word(0.0, 0.5, " xin"), Word(0.5, 1.0, " chào")]
    before = _word_tuples(original)
    calls = iter([
        ["$TRANSFORM_CASE_CAPITAL", "$APPEND_."],
        ["$KEEP", "$KEEP"],
    ])
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate, "_predict_actions", lambda pieces, runtime, progress_cb=None: next(calls)
    )
    result = punctuate.restore(original)
    assert result.applied is True and result.warning is None
    assert _word_tuples(result.words) == [(0.0, 0.5, " Xin"), (0.5, 1.0, " chào.")]
    assert _word_tuples(original) == before


def test_restore_preserves_existing_punctuation_and_multi_token_word(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 2.0, " hà nội, việt nam")]
    calls = iter([
        ["$TRANSFORM_CASE_CAPITAL", "$APPEND_.", "$TRANSFORM_CASE_CAPITAL", "$KEEP"],
        ["$KEEP", "$KEEP", "$KEEP", "$KEEP"],
    ])
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate, "_predict_actions", lambda pieces, runtime, progress_cb=None: next(calls)
    )
    result = punctuate.restore(words)
    assert _word_tuples(result.words) == [(0.0, 2.0, " Hà nội, Việt nam")]


def test_restore_falls_back_whole_input_on_any_error(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên bản")]
    monkeypatch.setattr(
        punctuate, "_load_runtime", lambda: (_ for _ in ()).throw(RuntimeError("secret path"))
    )
    result = punctuate.restore(words)
    assert result.applied is False
    assert _word_tuples(result.words) == _word_tuples(words)
    assert result.warning == (
        "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."
    )
    assert "secret" not in result.warning


def test_restore_falls_back_when_final_invariant_breaks(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên")]
    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(
        punctuate,
        "_predict_actions",
        lambda pieces, runtime, progress_cb=None: ["$KEEP"],
    )
    monkeypatch.setattr(
        punctuate,
        "_rebuild_words",
        lambda words, layouts, pieces: [Word(0.0, 1.0, " từ-khác")],
    )
    result = punctuate.restore(words)
    assert result.applied is False
    assert _word_tuples(result.words) == _word_tuples(words)


def test_restore_empty_does_not_load_runtime(monkeypatch):
    from app import punctuate

    monkeypatch.setattr(
        punctuate, "_load_runtime", lambda: (_ for _ in ()).throw(AssertionError())
    )
    result = punctuate.restore([])
    assert result == punctuate.PunctuationResult([], False, None)


def test_overlap_prefers_prediction_furthest_from_chunk_edge():
    from app.punctuate import _choose_overlapping

    chosen = _choose_overlapping(60, [
        (0, 48, ["$KEEP"] * 48),
        (36, 60, ["$APPEND_."] * 24),
    ])
    assert chosen[36] == "$KEEP"
    assert chosen[47] == "$APPEND_."


def test_predict_actions_builds_word_offsets_for_onnx():
    import numpy as np

    from app import punctuate

    class Encoding:
        ids = [101, 11, 12, 102]
        attention_mask = [1, 1, 1, 1]
        type_ids = [0, 0, 0, 0]
        word_ids = [None, 0, 1, None]

    class Tokenizer:
        def encode(self, tokens, is_pretokenized):
            assert tokens == ["xin", "chào"]
            assert is_pretokenized is True
            return Encoding()

    class Session:
        def __init__(self):
            self.feeds = None

        def run(self, outputs, feeds):
            self.feeds = feeds
            logits = np.zeros((1, 2, 15), dtype=np.float32)
            logits[0, 0, 3] = 10.0
            logits[0, 1, 0] = 10.0
            return [logits, np.zeros((1, 2, 4), dtype=np.float32)]

    _, pieces = punctuate._parse_words([
        Word(0.0, 0.5, " xin"), Word(0.5, 1.0, " chào")
    ])
    session = Session()
    runtime = punctuate._Runtime(session, Tokenizer(), punctuate._EXPECTED_LABELS)
    assert punctuate._predict_actions(pieces, runtime) == ["$APPEND_.", "$KEEP"]
    assert session.feeds["input_offsets"].tolist() == [[1, 2]]
