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
