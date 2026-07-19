import tempfile
from pathlib import Path

from app.diarize import SpeakerTurn, merge_minor_speakers
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


def test_merge_minor_speakers_collapses_noise_ids():
    """Hai speaker chính + nhiều id 'nhiễu' ngắn → còn 2 người sau merge."""
    turns = [
        SpeakerTurn(0.0, 10.0, 0),  # major A
        SpeakerTurn(10.0, 10.3, 5),  # noise
        SpeakerTurn(10.3, 20.0, 1),  # major B
        SpeakerTurn(20.0, 20.2, 99),  # noise
        SpeakerTurn(20.2, 30.0, 0),  # major A
        SpeakerTurn(30.0, 40.0, 1),  # major B
    ]
    merged = merge_minor_speakers(turns, min_share=0.05, max_speakers=8)
    ids = {t.speaker for t in merged}
    assert ids == {0, 1}
    # Thời lượng gần như giữ nguyên (chỉ gộp nhãn)
    assert abs(sum(t.end - t.start for t in merged) - 40.0) < 1e-6


def test_merge_minor_speakers_respects_max_speakers():
    turns = [SpeakerTurn(float(i), float(i) + 1.0, i) for i in range(20)]
    merged = merge_minor_speakers(turns, min_share=0.0, max_speakers=3)
    assert len({t.speaker for t in merged}) <= 3


def test_read_wav16k_float32_chunked(tmp_path):
    import wave

    import numpy as np

    from app.media import read_wav16k_float32

    samples = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(samples.tobytes())
    # _chunk_frames=2 ép đọc thành 3 khối — kiểm tra ráp khối đúng biên
    out = read_wav16k_float32(p, _chunk_frames=2)
    assert out.dtype == np.float32
    assert np.allclose(out, samples.astype(np.float32) / 32768.0)


def test_read_wav16k_float32_rejects_wrong_rate(tmp_path):
    import wave

    import numpy as np
    import pytest

    from app.media import read_wav16k_float32

    p = tmp_path / "bad.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(np.zeros(10, dtype=np.int16).tobytes())
    with pytest.raises(ValueError):
        read_wav16k_float32(p)


def test_duration_seconds_reads_wav(tmp_path):
    import wave

    import numpy as np

    from app.media import duration_seconds

    p = tmp_path / "one_sec.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(16000, dtype=np.int16).tobytes())  # đúng 1.0s
    d = duration_seconds(p)
    assert d is not None and abs(d - 1.0) < 0.05
    # File không tồn tại → None, không raise
    assert duration_seconds(tmp_path / "khong_ton_tai.mp3") is None


def test_checkpoint_roundtrip(tmp_path):
    from app import checkpoint
    from app.transcribe import Word

    p = tmp_path / "partial.jsonl"
    checkpoint.append_words(p, [Word(0.0, 1.0, " xin"), Word(1.0, 2.0, " chào.")])
    checkpoint.append_words(p, [Word(2.5, 3.0, " Huy")])
    words = checkpoint.load_words(p)
    assert [(w.start, w.end, w.text) for w in words] == [
        (0.0, 1.0, " xin"), (1.0, 2.0, " chào."), (2.5, 3.0, " Huy"),
    ]


def test_checkpoint_skips_corrupt_last_line(tmp_path):
    from app import checkpoint

    p = tmp_path / "partial.jsonl"
    p.write_text(
        '{"start": 0.0, "end": 1.0, "text": " ok"}\n{"start": 1.0, "en',  # crash giữa dòng
        encoding="utf-8",
    )
    words = checkpoint.load_words(p)
    assert len(words) == 1 and words[0].text == " ok"
    # File không tồn tại → list rỗng, không raise
    assert checkpoint.load_words(tmp_path / "missing.jsonl") == []


def test_transcribe_calls_segment_cb(monkeypatch, tmp_path):
    from app import transcribe as tr

    class _W:
        def __init__(self, s, e, t):
            self.start, self.end, self.word = s, e, t

    class _Seg:
        def __init__(self, s, e, words):
            self.start, self.end, self.text = s, e, ""
            self.words = words

    class _FakeModel:
        def transcribe(self, *a, **k):
            return iter([_Seg(0, 1, [_W(0, 0.5, " xin"), _W(0.5, 1, " chào.")]),
                         _Seg(1, 2, [_W(1, 2, " Huy.")])]), None

    batches = []
    words = tr.transcribe(_FakeModel(), tmp_path / "x.wav", 2.0,
                          segment_cb=lambda ws: batches.append(list(ws)))
    assert len(words) == 3
    assert [len(b) for b in batches] == [2, 1]  # mỗi segment 1 lần gọi


def test_pipeline_writes_partial_checkpoint(monkeypatch, tmp_path):
    from app import config, media, pipeline
    from app import transcribe as tr
    from app.transcribe import Word

    monkeypatch.setattr(media, "to_wav16k", lambda i, o: o)
    monkeypatch.setattr(media, "wav_duration_seconds", lambda p: 2.0)
    monkeypatch.setattr(config, "model_is_downloaded", lambda k: True)
    monkeypatch.setattr(tr, "load_model", lambda k: object())

    def fake_transcribe(model, wav, duration, segment_cb=None, **kw):
        ws = [Word(0.0, 1.0, " xin"), Word(1.0, 2.0, " chào.")]
        if segment_cb:
            segment_cb(ws)
        return ws

    monkeypatch.setattr(tr, "transcribe", fake_transcribe)
    result = pipeline.run(tmp_path / "in.wav", tmp_path, "phowhisper-small",
                          enable_diarization=False, enable_punctuation=False)
    assert (tmp_path / "partial.jsonl").exists()
    assert len(result["sentences"]) == 1


def test_long_audio_policy():
    import pytest
    from fastapi import HTTPException

    from app.server import _long_audio_policy

    assert _long_audio_policy(600.0, True) == (True, None)          # 10 phút: giữ nguyên
    assert _long_audio_policy(None, True) == (True, None)           # không đo được: giữ nguyên
    d, note = _long_audio_policy(3 * 3600.0, True)                  # 3 giờ: tắt diarize + note
    assert d is False and note and "phân biệt người nói" in note
    assert _long_audio_policy(3 * 3600.0, False) == (False, None)   # 3 giờ, diarize đã tắt sẵn
    with pytest.raises(HTTPException) as ei:                        # 5 giờ: từ chối
        _long_audio_policy(5 * 3600.0, False)
    assert ei.value.status_code == 400


def test_get_job_recovers_partial_from_disk(monkeypatch, tmp_path):
    import json

    from app import config, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    job_id = "deadbeef0001"
    jd = tmp_path / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "status.json").write_text(json.dumps({
        "status": "running", "stage": "transcribe", "percent": 40,
        "message": "…", "filename": "hop.mp3", "model": "phowhisper-small",
    }), encoding="utf-8")
    (jd / "partial.jsonl").write_text(
        '{"start": 0.0, "end": 1.0, "text": " Xin chào."}\n', encoding="utf-8")

    job = server._get_job(job_id)
    assert job["status"] == "error"
    assert job.get("partial") is True
    assert job["result"]["sentences"][0]["text"] == "Xin chào."
    assert job["result"]["model"] == "phowhisper-small"


def test_get_job_dead_without_partial(monkeypatch, tmp_path):
    import json

    from app import config, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    job_id = "deadbeef0002"
    jd = tmp_path / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "status.json").write_text(json.dumps({
        "status": "running", "stage": "model", "percent": 6,
        "message": "…", "filename": "hop.mp3", "model": "phowhisper-small",
    }), encoding="utf-8")
    job = server._get_job(job_id)
    assert job["status"] == "error" and "result" not in job


def test_apply_speaker_overrides():
    from app.segment import Sentence
    from app.server import _apply_speaker_overrides

    sents = [Sentence(0, 1, "a", 0), Sentence(1, 2, "b", 1), Sentence(2, 3, "c", 1)]
    _apply_speaker_overrides(sents, {
        "2": 0,        # hợp lệ → đổi
        "0": 5,        # speaker 5 không tồn tại → bỏ qua
        "99": 1,       # index ngoài biên → bỏ qua
        "bad": 1,      # index rác → bỏ qua
        "1": "x",      # speaker rác → bỏ qua
    })
    assert [s.speaker for s in sents] == [0, 1, 0]
    # None và rỗng không đổ vỡ
    _apply_speaker_overrides(sents, None)
    _apply_speaker_overrides(sents, {})


def test_export_srt_with_speaker_override(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app import config, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    job_id = "spkoverride01"
    (tmp_path / "jobs" / job_id).mkdir(parents=True)
    server.JOBS[job_id] = {
        "status": "done", "filename": "hop.mp3",
        "result": {"sentences": [
            {"start": 0.0, "end": 1.0, "text": "Xin chào.", "speaker": 0},
            {"start": 1.0, "end": 2.0, "text": "Chào bạn.", "speaker": 1},
        ], "duration": 2.0, "num_speakers": 2, "extracted_audio": None, "model": "x"},
    }
    try:
        c = TestClient(server.app)
        r = c.post(f"/api/jobs/{job_id}/export",
                   json={"format": "srt", "speakers": {"1": 0}})
        assert r.status_code == 200
        srt = (tmp_path / "jobs" / job_id / "hop.srt").read_text(encoding="utf-8")
        assert "Người nói 1: Chào bạn." in srt  # dòng 2 đã đổi từ speaker 1 → 0
    finally:
        server.JOBS.pop(job_id, None)
