import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

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


def test_ensure_model_dir_rejects_corrupted_cached_file(monkeypatch, tmp_path):
    from app import config, punctuate

    payload = b"abc"
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(config.PUNCTUATION_MODEL, "size", len(payload))
    monkeypatch.setitem(
        config.PUNCTUATION_MODEL, "sha256", hashlib.sha256(payload).hexdigest()
    )
    root = config.punctuation_dir()
    # Đúng size, sai bytes — manifest hợp lệ nên punctuation_is_downloaded() True.
    (root / config.PUNCTUATION_MODEL["filename"]).write_bytes(b"xyz")
    config.punctuation_manifest_path().write_text(
        json.dumps({
            "revision": config.PUNCTUATION_MODEL["revision"],
            "sha256": config.PUNCTUATION_MODEL["sha256"],
        }),
        encoding="utf-8",
    )

    def forbidden_download(**kwargs):
        raise AssertionError("không được tải lại khi cache đã đầy đủ")

    monkeypatch.setattr(punctuate, "_snapshot_download", forbidden_download)
    with pytest.raises(RuntimeError, match="SHA-256"):
        punctuate._ensure_model_dir()


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
    # Chỉ đổi đúng một ký tự — casing giữa từ do ASR/glossary tạo ra phải sống sót.
    assert _apply_case("iPhone", "$TRANSFORM_CASE_CAPITAL") == "IPhone"
    assert _apply_case("VNExpress", "$TRANSFORM_CASE_CAPITAL") == "VNExpress"
    assert _apply_case("iphoneX", "$TRANSFORM_CASE_CAPITAL_1") == "iPhoneX"
    assert _apply_case("", "$TRANSFORM_CASE_CAPITAL") == ""
    assert _apply_case("a", "$TRANSFORM_CASE_CAPITAL_1") == "a"


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
        (["$TRANSFORM_CASE_CAPITAL", "$APPEND_."], 0),
        (["$KEEP", "$KEEP"], 0),
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
        (["$TRANSFORM_CASE_CAPITAL", "$APPEND_.", "$TRANSFORM_CASE_CAPITAL", "$KEEP"], 0),
        (["$KEEP", "$KEEP", "$KEEP", "$KEEP"], 0),
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
        lambda pieces, runtime, progress_cb=None: (["$KEEP"], 0),
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


def test_restore_refines_until_a_pass_changes_nothing(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " hà"), Word(1.0, 2.0, " nội")]
    seen: list[list[str]] = []

    def fake_predict(pieces, runtime, progress_cb=None):
        seen.append([piece.output_core + piece.suffix for piece in pieces])
        if len(seen) == 1:
            return ["$TRANSFORM_CASE_CAPITAL", "$TRANSFORM_CASE_CAPITAL"], 0
        if len(seen) == 2:
            return ["$KEEP", "$APPEND_."], 0
        return ["$KEEP", "$KEEP"], 0

    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(punctuate, "_predict_actions", fake_predict)
    result = punctuate.restore(words)
    assert [word.text for word in result.words] == [" Hà", " Nội."]
    # Pass 2 phải nhìn thấy kết quả pass 1 — đó là lý do vòng lặp tồn tại.
    assert seen == [["hà", "nội"], ["Hà", "Nội"], ["Hà", "Nội."]]


def test_restore_stops_after_first_pass_when_nothing_changes(monkeypatch):
    from app import punctuate

    words = [Word(0.0, 1.0, " nguyên")]
    calls = []

    def fake_predict(pieces, runtime, progress_cb=None):
        calls.append(1)
        return ["$KEEP"], 0

    monkeypatch.setattr(punctuate, "_load_runtime", lambda: object())
    monkeypatch.setattr(punctuate, "_predict_actions", fake_predict)
    result = punctuate.restore(words)
    assert result.applied is True
    assert len(calls) == 1


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
    actions, failed = punctuate._predict_actions(pieces, runtime)
    assert actions == ["$APPEND_.", "$KEEP"]
    assert failed == 0
    assert session.feeds["input_offsets"].tolist() == [[1, 2]]


@pytest.mark.model
def test_real_punctuation_model_contract():
    from app import config, punctuate

    words = [
        Word(float(i), float(i + 1), " " + token)
        for i, token in enumerate("hà nội là thủ đô việt nam tôi yêu nó".split())
    ]
    result = punctuate.restore(words)
    text = "".join(word.text for word in result.words).strip()
    assert result.applied is True, result.warning
    assert config.punctuation_is_downloaded() is True
    assert any(mark in text for mark in ".,:?")
    assert any(char.isupper() for char in text)
    assert punctuate._invariants_hold(words, result.words)


def test_pipeline_punctuates_before_sentence_split(monkeypatch, tmp_path):
    from app import config, media, pipeline, punctuate, transcribe

    monkeypatch.setattr(media, "to_wav16k", lambda source, out: out)
    monkeypatch.setattr(media, "wav_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: True)
    monkeypatch.setattr(config, "punctuation_is_downloaded", lambda: True)
    monkeypatch.setattr(config, "load_settings", lambda: {"beam_size": 5})
    monkeypatch.setattr(transcribe, "load_model", lambda key: object())
    monkeypatch.setattr(
        transcribe,
        "transcribe",
        lambda *args, **kwargs: [
            Word(0.0, 1.0, " xin"),
            Word(1.0, 2.0, " chào"),
            Word(2.0, 3.0, " bạn"),
        ],
    )
    monkeypatch.setattr(
        punctuate,
        "restore",
        lambda words, progress_cb=None: punctuate.PunctuationResult(
            [Word(0.0, 1.0, " Xin."), Word(1.0, 2.0, " chào"), Word(2.0, 3.0, " bạn.")],
            True,
            None,
        ),
    )
    result = pipeline.run(
        tmp_path / "in.wav", tmp_path, "phowhisper-small",
        enable_diarization=False, enable_punctuation=True,
    )
    assert [row["text"] for row in result["sentences"]] == ["Xin.", "chào bạn."]
    assert result["punctuation"]["applied"] is True


def test_pipeline_disabled_does_not_call_punctuation(monkeypatch, tmp_path):
    from app import config, media, pipeline, punctuate, transcribe

    monkeypatch.setattr(media, "to_wav16k", lambda source, out: out)
    monkeypatch.setattr(media, "wav_duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: True)
    monkeypatch.setattr(config, "load_settings", lambda: {"beam_size": 5})
    monkeypatch.setattr(transcribe, "load_model", lambda key: object())
    monkeypatch.setattr(
        transcribe, "transcribe", lambda *args, **kwargs: [Word(0.0, 1.0, " nguyên")]
    )
    monkeypatch.setattr(
        punctuate, "restore", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError())
    )
    result = pipeline.run(
        tmp_path / "in.wav", tmp_path, "phowhisper-small",
        enable_diarization=False, enable_punctuation=False,
    )
    assert result["punctuation"] == {
        "requested": False,
        "applied": False,
        "backend": "vibert-capu-onnx-int8",
        "warning": None,
    }


def test_meta_exposes_punctuation_model(monkeypatch):
    from fastapi.testclient import TestClient

    from app import config, server

    monkeypatch.setattr(config, "punctuation_is_downloaded", lambda: True)
    monkeypatch.setattr(config, "model_is_downloaded", lambda key: False)
    monkeypatch.setattr(config, "load_settings", lambda: {"punctuate": True})
    monkeypatch.setattr(config, "load_glossary_text", lambda: "")
    payload = TestClient(server.app).get("/api/meta").json()["punctuation"]
    assert payload == {"downloaded": True, "size": "~110 MB", "license": "CC-BY-SA-4.0"}


def test_create_job_passes_and_persists_punctuate(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app import config, media, server

    captured = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            captured["opts"] = args[2]

        def start(self):
            return None

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(media, "duration_seconds", lambda path: 1.0)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)
    server.JOBS.clear()
    try:
        response = TestClient(server.app).post(
            "/api/jobs",
            files={"file": ("hop.wav", b"RIFF", "audio/wav")},
            data={"model": "phowhisper-small", "punctuate": "false"},
        )
        assert response.status_code == 200
        assert captured["opts"]["punctuate"] is False
        assert config.load_settings()["punctuate"] is False

        server.JOBS.clear()
        response = TestClient(server.app).post(
            "/api/jobs",
            files={"file": ("hop.wav", b"RIFF", "audio/wav")},
            data={"model": "phowhisper-small"},
        )
        assert response.status_code == 200
        assert captured["opts"]["punctuate"] is True
    finally:
        server.JOBS.clear()


def test_run_job_appends_punctuation_warning_to_existing_note(monkeypatch, tmp_path):
    from app import config, pipeline, server

    job_id = "punctwarn001"
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    server.JOBS[job_id] = {"status": "running", "note": "Đã tắt diarization."}
    monkeypatch.setattr(
        pipeline,
        "run",
        lambda *args, **kwargs: {
            "sentences": [], "duration": 1.0, "punctuation": {
                "warning": (
                    "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên."
                )
            },
        },
    )
    server._run_job(job_id, tmp_path / "in.wav", {
        "model": "phowhisper-small", "language": "vi", "diarize": False,
        "punctuate": True, "num_speakers": 0, "glossary": "",
    })
    # Job đã kết thúc: không còn trong RAM, nguồn chân lý là status.json
    assert job_id not in server.JOBS
    job = server._get_job(job_id)
    assert job["status"] == "done"
    assert job["note"].splitlines() == [
        "Đã tắt diarization.",
        "Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên.",
    ]


def _input_attrs(html: str, element_id: str) -> dict[str, str]:
    class Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.found: dict[str, str] | None = None

        def handle_starttag(self, tag, attrs):
            data = {key: (value if value is not None else "") for key, value in attrs}
            if data.get("id") == element_id:
                self.found = data

    parser = Collector()
    parser.feed(html)
    assert parser.found is not None, f"không tìm thấy element id={element_id}"
    return parser.found


def test_ui_contains_punctuation_checkbox_and_form_contract():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    attrs = _input_attrs(html, "punctuate")
    assert attrs["type"] == "checkbox"
    assert "checked" in attrs

    assert "Tự chèn dấu câu (khuyên dùng cho PhoWhisper)" in html
    assert 'fd.append("punctuate", punctuateEl.checked ? "true" : "false")' in html
    assert "settings.punctuate" in html
    assert "punctuationMeta.downloaded" in html


def test_predict_actions_skips_only_the_failing_chunk(monkeypatch):
    from app import punctuate

    pieces = [
        punctuate._Piece(word_index=i, span_index=0, model_core=f"w{i}",
                         output_core=f"w{i}", suffix="")
        for i in range(60)
    ]
    calls = []

    def fake_encode(runtime, chunk):
        calls.append(len(chunk))
        if len(calls) == 1:
            raise KeyError("token bi tokenizer nuot")
        return {}

    class FakeSession:
        def run(self, names, feeds):
            import numpy as np
            # chunk thu hai: 24 vi tri (36..60), tra ve $APPEND_. cho tat ca
            return [np.tile(np.eye(len(punctuate._EXPECTED_LABELS))[3], (24, 1))[None, ...]]

    runtime = punctuate._Runtime(
        session=FakeSession(), tokenizer=object(), labels=punctuate._EXPECTED_LABELS
    )
    monkeypatch.setattr(punctuate, "_encode_chunk", fake_encode)

    actions, failed = punctuate._predict_actions(pieces, runtime)

    assert failed == 1
    assert len(actions) == 60
    assert actions[0] == "$KEEP"        # chunk loi -> giu nguyen
    assert actions[59] == "$APPEND_."   # chunk lanh van duoc ap dung


def test_predict_actions_raises_when_every_chunk_fails(monkeypatch):
    from app import punctuate

    pieces = [
        punctuate._Piece(word_index=i, span_index=0, model_core=f"w{i}",
                         output_core=f"w{i}", suffix="")
        for i in range(60)
    ]

    def always_fail(runtime, chunk):
        raise KeyError("hong")

    monkeypatch.setattr(punctuate, "_encode_chunk", always_fail)
    runtime = punctuate._Runtime(
        session=object(), tokenizer=object(), labels=punctuate._EXPECTED_LABELS
    )

    with pytest.raises(RuntimeError):
        punctuate._predict_actions(pieces, runtime)


def _load_eval_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval_punctuation", Path("scripts/eval_punctuation.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sentence_boundaries_ignores_duplicate_end_timestamps():
    module = _load_eval_module()
    words = [
        Word(0.0, 1.0, " a."),
        Word(1.0, 1.0, " b"),
        Word(1.0, 2.0, " c."),
    ]
    # Word 1 trùng end với ranh giới câu đầu nhưng KHÔNG phải ranh giới.
    assert module.sentence_boundaries(words) == {0, 2}
