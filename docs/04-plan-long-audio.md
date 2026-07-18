# Plan: Chịu tải file dài — không crash, không mất trắng kết quả

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** File audio/video dài (1–4 giờ) chạy được trên máy CPU yếu mà không bị OOM-kill, và nếu process chết giữa chừng thì người dùng vẫn nhận được phần transcript đã làm xong thay vì mất trắng.

**Architecture:** Ba lớp bảo vệ độc lập: (B) giảm đỉnh RAM khi đọc WAV cho diarization (đọc theo khối vào mảng float32 cấp phát sẵn — đỉnh giảm ~2.5×); (A) checkpoint transcript từng segment ra `partial.jsonl` trong job dir ngay khi faster-whisper nhả ra, server khôi phục thành kết quả "một phần" khi phát hiện job chết; (C) đo thời lượng file bằng ffprobe ngay sau upload và áp chính sách: quá 4 giờ → từ chối kèm hướng dẫn, 2–4 giờ → tự tắt diarization kèm ghi chú hiển thị cho người dùng.

**Tech Stack:** Không thêm dependency mới. Dùng `wave` + `numpy` (đã có), `ffprobe` (đi kèm ffmpeg hệ thống hoặc `static-ffmpeg` đã có), JSONL thuần `json`.

**Ngoài phạm vi (làm sau, cần brainstorm riêng):** transcribe theo cửa sổ (chunked) và resume từ checkpoint sau restart — đụng tới stitching speaker-ID giữa các cửa sổ diarization, là thay đổi kiến trúc pipeline.

## Global Constraints

- Kế thừa toàn bộ Global Constraints của [02-plan.md](02-plan.md) (Python 3.10–3.12, không PyTorch, CPU int8, text người dùng tiếng Việt, bind `127.0.0.1`, 1 job/lần, quy trình ruff → verify → commit)
- Commit message kết thúc bằng dòng `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Ngưỡng chính sách file dài là hằng số module-level trong `app/server.py` để dễ chỉnh: `_MAX_INPUT_SECONDS = 14_400` (4 giờ), `_MAX_DIARIZE_SECONDS = 7_200` (2 giờ)
- `partial.jsonl` ghi ở chế độ append từng segment; dòng cuối có thể bị cắt dở khi crash — parser PHẢI bỏ qua dòng hỏng, không raise
- Không đổi format `status.json` theo kiểu phá vỡ ngược: chỉ THÊM key mới (`model`, `note`)

---

### Task 1: Giảm đỉnh RAM `read_wav16k_float32` (đọc theo khối)

**Files:**
- Modify: `app/media.py:59-66` (hàm `read_wav16k_float32`)
- Test: `tests/test_core.py` (thêm 2 test)

**Interfaces:**
- Produces: `media.read_wav16k_float32(wav_path: Path, _chunk_frames: int = 960_000) -> np.ndarray` — giữ nguyên chữ ký cũ (tham số mới có default), giá trị trả về giống hệt trước (float32 mono [-1, 1]). `diarize.diarize` không cần sửa.

- [ ] **Step 1: Viết 2 test fail**

Thêm vào cuối `tests/test_core.py`:

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py -k read_wav16k -v`
Expected: `test_read_wav16k_float32_chunked` FAIL — `TypeError: ... unexpected keyword argument '_chunk_frames'` (test reject-rate có thể pass sẵn vì đã raise ValueError)

- [ ] **Step 3: Viết lại `read_wav16k_float32`**

Thay toàn bộ hàm trong `app/media.py`:

```python
def read_wav16k_float32(wav_path: Path, _chunk_frames: int = 960_000):
    """Đọc WAV 16kHz mono thành mảng float32 [-1, 1] cho sherpa-onnx.

    Đọc theo khối (mặc định 60s/khối) vào mảng float32 cấp phát sẵn:
    file 3 giờ chỉ tốn ~4 B/sample thay vì ~10 B/sample đỉnh như đọc một cục
    (bytes int16 + bản astype + bản kết quả phép chia).
    """
    import numpy as np

    with wave.open(str(wav_path), "rb") as w:
        # Không dùng assert: sẽ bị bỏ qua khi chạy python -O, khiến WAV sai định dạng
        # bị đọc thành mẫu rác cho diarization.
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("WAV phải là 16kHz mono")
        n = w.getnframes()
        out = np.empty(n, dtype=np.float32)
        pos = 0
        while pos < n:
            data = w.readframes(min(_chunk_frames, n - pos))
            block = np.frombuffer(data, dtype=np.int16)
            out[pos : pos + len(block)] = block
            pos += len(block)
    out /= 32768.0  # in-place, không tạo mảng mới
    return out
```

- [ ] **Step 4: Chạy toàn bộ test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 12 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add app/media.py tests/test_core.py
git commit -m "perf: doc WAV theo khoi — giam ~2.5x dinh RAM cho diarization file dai

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Đo thời lượng file bằng ffprobe

**Files:**
- Modify: `app/media.py` (thêm `ffprobe_path` + `duration_seconds`)
- Test: `tests/test_core.py` (thêm 1 test)

**Interfaces:**
- Consumes: `ffmpeg_path()` pattern sẵn có trong `app/media.py:11-18`
- Produces: `media.duration_seconds(path: Path) -> float | None` — trả về thời lượng giây của MỌI định dạng audio/video ffprobe đọc được; trả về `None` (không raise) khi ffprobe lỗi/không đọc được. Task 5 dùng hàm này.

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_core.py`:

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py::test_duration_seconds_reads_wav -v`
Expected: FAIL — `ImportError: cannot import name 'duration_seconds'`

- [ ] **Step 3: Thêm vào `app/media.py`** (ngay dưới `ffmpeg_path`)

```python
def ffprobe_path() -> str:
    """Như ffmpeg_path nhưng cho ffprobe (static-ffmpeg trả về cặp (ffmpeg, ffprobe))."""
    found = shutil.which("ffprobe")
    if found:
        return found
    import static_ffmpeg.run

    return static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()[1]


def duration_seconds(path: Path) -> float | None:
    """Thời lượng file (giây) qua ffprobe. Trả về None nếu không đọc được — caller tự quyết."""
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None
```

- [ ] **Step 4: Chạy test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 13 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add app/media.py tests/test_core.py
git commit -m "feat: media.duration_seconds — do thoi luong file qua ffprobe

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Module checkpoint (JSONL từng phần)

**Files:**
- Create: `app/checkpoint.py`
- Test: `tests/test_core.py` (thêm 2 test)

**Interfaces:**
- Consumes: `Word(start: float, end: float, text: str)` từ `app/transcribe.py:13-17`
- Produces: `checkpoint.append_words(path: Path, words: list[Word]) -> None` (append, tạo file nếu chưa có) và `checkpoint.load_words(path: Path) -> list[Word]` (file thiếu/dòng hỏng → bỏ qua êm, trả `[]` nếu không có gì). Task 4 gọi `append_words`; Task 5 gọi `load_words`.

- [ ] **Step 1: Viết 2 test fail**

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py -k checkpoint -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.checkpoint'`

- [ ] **Step 3: Viết `app/checkpoint.py`**

```python
"""Checkpoint transcript từng phần ra đĩa (JSONL).

File dài chạy hàng giờ trên CPU — nếu process chết giữa chừng, partial.jsonl
giữ lại toàn bộ segment đã transcript xong để server dựng kết quả "một phần"
thay vì mất trắng. Mỗi dòng một JSON {start, end, text}; dòng cuối có thể bị
cắt dở khi crash nên parser bỏ qua dòng hỏng.
"""
import json
from pathlib import Path

from .transcribe import Word


def append_words(path: Path, words: list[Word]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for w in words:
            f.write(
                json.dumps(
                    {"start": w.start, "end": w.end, "text": w.text},
                    ensure_ascii=False,
                )
                + "\n"
            )


def load_words(path: Path) -> list[Word]:
    words: list[Word] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            words.append(Word(float(d["start"]), float(d["end"]), str(d["text"])))
        except (ValueError, KeyError, TypeError):
            continue  # dòng bị cắt dở lúc crash — bỏ qua
    return words
```

- [ ] **Step 4: Chạy test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 15 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add app/checkpoint.py tests/test_core.py
git commit -m "feat: module checkpoint JSONL — luu transcript tung phan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Nối checkpoint vào transcribe + pipeline

**Files:**
- Modify: `app/transcribe.py:39-70` (thêm tham số `segment_cb`)
- Modify: `app/pipeline.py` (ghi checkpoint khi transcribe)
- Test: `tests/test_core.py` (thêm 2 test)

**Interfaces:**
- Consumes: `checkpoint.append_words` (Task 3)
- Produces: `transcribe.transcribe(..., segment_cb: Callable[[list[Word]], None] | None = None)` — gọi `segment_cb(words_của_segment)` NGAY sau mỗi segment faster-whisper nhả ra. `pipeline.run` ghi `work_dir / "partial.jsonl"` (xóa file cũ lúc bắt đầu). Task 5 dựa vào vị trí file này: `jobs_dir()/<job_id>/partial.jsonl` (server truyền `work_dir = input_path.parent` = job dir, giữ nguyên như hiện tại).

- [ ] **Step 1: Viết 2 test fail**

```python
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
                          enable_diarization=False)
    assert (tmp_path / "partial.jsonl").exists()
    assert len(result["sentences"]) == 1
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py -k "segment_cb or partial_checkpoint" -v`
Expected: FAIL — `TypeError: transcribe() got an unexpected keyword argument 'segment_cb'`

- [ ] **Step 3: Sửa `app/transcribe.py`**

Chữ ký mới + thân vòng lặp (giữ nguyên phần còn lại):

```python
def transcribe(
    model,
    wav_path: Path,
    duration: float,
    language: str = "vi",
    beam_size: int = 5,
    initial_prompt: str | None = None,
    hotwords: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
    segment_cb: Callable[[list[Word]], None] | None = None,
) -> list[Word]:
    """Chạy transcript, trả về danh sách từ kèm timestamp (giây).

    segment_cb (nếu có) được gọi với danh sách Word của TỪNG segment ngay khi
    segment đó xong — dùng để checkpoint ra đĩa cho file dài.
    """
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
            new = [Word(w.start, w.end, w.word) for w in seg.words]
        else:
            new = [Word(seg.start, seg.end, seg.text)]
        words.extend(new)
        if segment_cb:
            segment_cb(new)
        if progress_cb and duration > 0:
            progress_cb(min(seg.end / duration, 1.0))
    return words
```

- [ ] **Step 4: Sửa `app/pipeline.py`**

Import thêm `checkpoint` (dòng 6: `from . import checkpoint, config, diarize, glossary, media, segment, transcribe`). Trong `run`, ngay trước bước 3 thêm khởi tạo, và thêm `segment_cb` vào lời gọi:

```python
    # 3. Transcribe (chiếm phần lớn thời gian) — checkpoint từng segment ra đĩa
    partial_path = work_dir / "partial.jsonl"
    partial_path.unlink(missing_ok=True)  # job chạy lại trong cùng dir không dính dữ liệu cũ
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
        segment_cb=lambda ws: checkpoint.append_words(partial_path, ws),
    )
```

- [ ] **Step 5: Chạy toàn bộ test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 17 passed, ruff sạch

- [ ] **Step 6: Commit**

```bash
git add app/transcribe.py app/pipeline.py tests/test_core.py
git commit -m "feat: checkpoint transcript tung segment ra partial.jsonl

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Server — chính sách file dài + khôi phục kết quả một phần

**Files:**
- Modify: `app/server.py` (policy, `model`/`note` trong job dict, recovery, cổng export)
- Test: `tests/test_core.py` (thêm 3 test)

**Interfaces:**
- Consumes: `media.duration_seconds` (Task 2), `checkpoint.load_words` (Task 3), `segment.build_sentences` sẵn có
- Produces: `server._long_audio_policy(duration: float | None, diarize: bool) -> tuple[bool, str | None]` — trả `(diarize_hiệu_lực, note_tiếng_Việt | None)`, raise `HTTPException(400)` nếu quá `_MAX_INPUT_SECONDS`. Job dict/status.json có thêm key `model` (str, ghi lúc tạo) và `note` (str, chỉ khi policy kích hoạt). Job chết-giữa-chừng có `partial.jsonl` → status trả về `status="error"` KÈM `result` (partial) + `partial: true`. Task 6 (UI) đọc `note`, `partial`, và `result` trong nhánh error.

- [ ] **Step 1: Viết 3 test fail**

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_core.py -k "long_audio_policy or recovers_partial or dead_without" -v`
Expected: FAIL — `ImportError: cannot import name '_long_audio_policy'`

- [ ] **Step 3: Sửa `app/server.py`**

(a) Import thêm ở đầu file: `from dataclasses import asdict` và đổi dòng import package thành `from . import checkpoint, config, export, media, pipeline, segment`.

(b) Hằng số + policy (đặt dưới `_FAVICON`):

```python
# Chính sách file dài — chống OOM trên máy CPU yếu (xem docs/04-plan-long-audio.md)
_MAX_INPUT_SECONDS = 14_400  # 4 giờ: từ chối, khuyên cắt file
_MAX_DIARIZE_SECONDS = 7_200  # 2 giờ: tự tắt diarization


def _long_audio_policy(duration: float | None, diarize: bool) -> tuple[bool, str | None]:
    """Trả về (diarize hiệu lực, ghi chú cho người dùng). Raise 400 nếu file quá dài."""
    if duration is None:
        return diarize, None  # không đo được thời lượng — không chặn
    if duration > _MAX_INPUT_SECONDS:
        raise HTTPException(
            400,
            f"File dài {duration / 3600:.1f} giờ — vượt giới hạn 4 giờ. "
            "Hãy cắt file thành các phần ngắn hơn (ví dụ bằng QuickTime/ffmpeg) rồi chạy từng phần.",
        )
    if diarize and duration > _MAX_DIARIZE_SECONDS:
        return False, (
            f"File dài {duration / 3600:.1f} giờ nên đã tự tắt phân biệt người nói "
            "để tránh hết bộ nhớ. Transcript và timestamp vẫn đầy đủ."
        )
    return diarize, None
```

(c) Trong `create_job`: thêm `"model": model` vào job dict lúc tạo; trong khối `try` (sau khi ghi xong file upload, trước `save_settings`) thêm:

```python
        duration = media.duration_seconds(input_path)
        diarize, note = _long_audio_policy(duration, diarize)
        if note:
            with _JOBS_LOCK:
                JOBS[job_id]["note"] = note
            _save_job(job_id, JOBS[job_id])
```

(HTTPException từ policy nằm trong `try` → `except Exception` sẵn có nhả chỗ `JOBS.pop` rồi re-raise — đúng hành vi cần.)

(d) Trong `_get_job`, nhánh `disk.get("status") == "running"` — dựng kết quả một phần:

```python
        if disk.get("status") == "running":
            disk["status"] = "error"
            disk["percent"] = 100
            words = checkpoint.load_words(_status_path(job_id).parent / "partial.jsonl")
            if words:
                sentences = segment.build_sentences(words)
                disk["partial"] = True
                disk["result"] = {
                    "sentences": [asdict(s) for s in sentences],
                    "duration": words[-1].end,
                    "num_speakers": 0,
                    "extracted_audio": None,
                    "model": disk.get("model", "?"),
                }
                disk["message"] = (
                    "Server đã dừng giữa chừng — nhưng phần transcript làm xong "
                    f"({len(sentences)} câu, tới phút {words[-1].end / 60:.0f}) đã được khôi phục bên dưới. "
                    "Chạy lại file để có bản đầy đủ."
                )
            else:
                disk["message"] = (
                    "Server đã dừng giữa chừng (process bị tắt). "
                    "Hãy bấm Bắt đầu lại — model đã tải sẵn nên lần sau nhanh hơn."
                )
            _save_job(job_id, disk)
```

(e) Cổng export chấp nhận kết quả một phần — thay 2 dòng đầu `export_job`:

```python
    job = _get_job(job_id)
    if not (job.get("result") or {}).get("sentences"):
        raise HTTPException(409, "Job chưa xong")
```

- [ ] **Step 4: Chạy toàn bộ test + ruff**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 20 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add app/server.py tests/test_core.py
git commit -m "feat: chinh sach file dai + khoi phuc transcript mot phan tu partial.jsonl

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: UI — hiển thị ghi chú policy + kết quả một phần

**Files:**
- Modify: `app/static/index.html` (thêm `noteBox`, sửa `pollJob`, reset khi start)

**Interfaces:**
- Consumes: key `note`, `partial`, `result` trong JSON job status (Task 5)
- Produces: UI hiển thị note màu nhạt dưới progress; khi `status="error"` mà có `result.sentences` thì vẫn render bảng kết quả (kèm thông báo lỗi phía trên)

- [ ] **Step 1: Thêm phần tử note vào HTML**

Ngay SAU `<div class="error" id="errorBox"></div>` (dòng ~312):

```html
      <div class="note" id="noteBox" hidden></div>
```

Và thêm CSS vào khối `<style>` (cạnh `.error`):

```css
    .note {
      margin-top: 10px; padding: 10px 12px; border-radius: 8px;
      background: #fff8e6; color: #7a5b00; font-size: 14px; line-height: 1.5;
    }
```

- [ ] **Step 2: Khai báo + helper trong JS**

Cạnh `const errorBox = $("errorBox");` thêm `const noteBox = $("noteBox");`. Cạnh `showError` thêm:

```js
      function showNote(msg) {
        noteBox.textContent = msg || "";
        noteBox.hidden = !msg;
      }
```

- [ ] **Step 3: Sửa `pollJob`** — sau dòng `setProgress(job.percent, job.message || "");` thêm `showNote(job.note);`, và thay nhánh error:

```js
          if (job.status === "error") {
            showError(job.message || "Lỗi không xác định");
            if (job.result && job.result.sentences && job.result.sentences.length) {
              showResults(job);  // kết quả một phần khôi phục từ checkpoint
            }
            return;
          }
```

- [ ] **Step 4: Reset khi bắt đầu job mới** — trong handler `startBtn` (chỗ đã có `names = {}; pollFailCount = 0;`) thêm `showNote(null);`

- [ ] **Step 5: Verify thủ công bằng TestClient + duyệt tay**

Run:
```bash
uv run python -c "
from fastapi.testclient import TestClient
from app.server import app
c = TestClient(app)
assert c.get('/').status_code == 200
assert 'noteBox' in c.get('/').text
print('UI OK')"
```
Expected: `UI OK`

Sau đó chạy `uv run python -m app.server`, upload 1 file audio ngắn, xác nhận UI vẫn chạy bình thường (note không hiện với file ngắn).

- [ ] **Step 6: Commit**

```bash
git add app/static/index.html
git commit -m "feat: UI hien thi ghi chu file dai va ket qua mot phan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Cập nhật tài liệu + nghiệm thu file dài

**Files:**
- Modify: `docs/05-tasks-long-audio.md` (điền trạng thái 🟢 từng task khi xong)
- Modify: `README.md` (mục "File dài": giới hạn 4 giờ, tự tắt diarize trên 2 giờ, khôi phục một phần)

**Interfaces:** không có — tài liệu.

- [ ] **Step 1: Thêm mục "File dài" vào README.md** (sau mục mô tả tính năng):

```markdown
## File dài (1–4 giờ)

- File **trên 2 giờ**: app tự tắt "phân biệt người nói" để tránh hết bộ nhớ — transcript và timestamp vẫn đầy đủ (có ghi chú vàng trên màn hình).
- File **trên 4 giờ**: app từ chối và khuyên cắt file thành phần ngắn hơn.
- Nếu app bị tắt giữa chừng (mất điện, đóng nhầm cửa sổ): mở lại app, phần transcript đã làm xong sẽ tự hiện lại — có thể xuất file ngay, hoặc chạy lại từ đầu để có bản đầy đủ.
```

- [ ] **Step 2: Nghiệm thu file dài thật** (cần file của người dùng, ≥ 2 giờ):

1. Upload file > 2 giờ → thấy ghi chú vàng "đã tự tắt phân biệt người nói", job chạy hết không OOM
2. Giữa chừng job, kill process (`kill -9 <pid>`), mở lại app, poll lại job cũ qua URL `/api/jobs/<id>` → thấy kết quả một phần + xuất DOCX được
3. Ghi kết quả vào bảng nghiệm thu trong `docs/05-tasks-long-audio.md`

- [ ] **Step 3: Commit**

```bash
git add README.md docs/05-tasks-long-audio.md
git commit -m "docs: huong dan file dai + ket qua nghiem thu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
