# Sửa lỗi từ review toàn bộ code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loại bỏ 3 lỗi khiến app kẹt không dùng được, siết an toàn khâu tải model diarization, và thu hẹp phạm vi hỏng của phục hồi dấu câu.

**Architecture:** Toàn bộ là sửa tại chỗ trong các module `app/` đã có — không thêm module, không đổi interface công khai, không đổi schema `status.json`. Mỗi task sửa một hành vi độc lập, có test riêng, commit riêng. Thứ tự task xếp theo mức nghiêm trọng: Task 1–3 là các lỗi làm app kẹt vĩnh viễn, Task 4–5 là an toàn/chất lượng, Task 6–8 là dọn dẹp.

**Tech Stack:** Python 3.12 (uv), pytest, faster-whisper, sherpa-onnx, onnxruntime, FastAPI, numpy.

## Global Constraints

- Worktree code: `/Users/huytv/Github/cba_Transcript_local/.worktrees/vitranscript-impl` — mọi đường dẫn dưới đây là tương đối so với thư mục này.
- Branch: `fix/review-findings` (tách từ `feature/long-audio-robustness`). Working tree sạch khi bắt đầu — **không được `git add -A`**, chỉ add đúng file mà task liệt kê.
- `requires-python = ">=3.10,<3.13"` — KHÔNG thêm dependency kéo PyTorch/TensorFlow.
- `uv run ruff check .` phải sạch trước mỗi commit (`line-length = 100`).
- `uv run pytest tests/ -q` phải pass toàn bộ trước mỗi commit. Baseline hiện tại: **46 passed, 1 deselected**.
- Text hướng tới người dùng: tiếng Việt có dấu. File `.bat` viết không dấu.
- URL diarization chứa `"speaker-recongition-models"` — lỗi chính tả CỐ Ý của upstream, không được "sửa".
- Server chỉ bind `127.0.0.1`.
- Commit message kết thúc bằng: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Chỉ commit vào branch `fix/review-findings`, không merge/push nếu chưa được yêu cầu.

---

### Task 1: Chặn vòng lặp vô hạn khi WAV bị cắt dở

Lỗi nghiêm trọng nhất. `read_wav16k_float32` lặp `while pos < n` dựa trên số frame **khai trong header**. Nếu file bị cắt dở (ffmpeg bị kill giữa lúc ghi `audio16k.wav` — máy sleep, hết disk, Ctrl+C), `readframes` trả về rỗng, `len(block)` bằng 0, `pos` không tiến → treo vĩnh viễn, ăn 100% CPU, không log gì. Vì server chỉ cho 1 job chạy, mọi job sau đó đều bị 409 vĩnh viễn.

Task này cũng thêm `pytest-timeout` vào dev deps: nếu không có, test dưới đây khi fail sẽ treo cả suite thay vì báo fail.

**Files:**
- Modify: `app/media.py:104-111`
- Modify: `pyproject.toml` (dev dependency group)
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có (task đầu tiên).
- Produces: `read_wav16k_float32(wav_path: Path, _chunk_frames: int = 960_000) -> np.ndarray` — chữ ký không đổi; hành vi mới là trả về mảng **ngắn hơn** header khai, thay vì treo.

- [ ] **Step 1: Thêm pytest-timeout vào dev deps**

Sửa `pyproject.toml`, mục `[dependency-groups]`:

```toml
[dependency-groups]
dev = ["pytest>=8", "pytest-timeout>=2.3", "ruff>=0.4", "jiwer>=3.0"]
```

Chạy: `uv sync`

- [ ] **Step 2: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`. Lưu ý phần import ở đầu file đã có `wave` chưa — nếu chưa, thêm `import struct` và `import wave` vào khối import đầu file, và `import pytest`.

```python
@pytest.mark.timeout(10)
def test_read_wav16k_float32_handles_truncated_file(tmp_path):
    # Mô phỏng ffmpeg bị kill giữa chừng: header khai 10 giây, dữ liệu thực chỉ 1 giây.
    p = tmp_path / "trunc.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x01" * 16000)
    raw = bytearray(p.read_bytes())
    i = raw.find(b"data")
    struct.pack_into("<I", raw, i + 4, 16000 * 2 * 10)
    p.write_bytes(bytes(raw))

    samples = read_wav16k_float32(p)

    assert len(samples) == 16000  # trả về đúng phần đọc được, không treo
```

- [ ] **Step 3: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py::test_read_wav16k_float32_handles_truncated_file -v`

Expected: FAIL với `Failed: Timeout >10.0s` (chứng minh vòng lặp vô hạn có thật).

- [ ] **Step 4: Sửa vòng lặp**

Trong `app/media.py`, thay khối `while pos < n:` bằng:

```python
        n = w.getnframes()
        out = np.empty(n, dtype=np.float32)
        pos = 0
        while pos < n:
            data = w.readframes(min(_chunk_frames, n - pos))
            block = np.frombuffer(data, dtype=np.int16)
            if len(block) == 0:
                # Header khai nhiều frame hơn dữ liệu thực (file bị cắt dở).
                # Không thoát ở đây thì pos đứng yên và vòng lặp chạy mãi.
                out = out[:pos]
                break
            out[pos : pos + len(block)] = block
            pos += len(block)
```

- [ ] **Step 5: Chạy test để xác nhận pass**

Run: `uv run pytest tests/test_core.py -q`

Expected: toàn bộ pass, trong đó có test mới.

- [ ] **Step 6: Lint và commit**

```bash
uv run ruff check .
git add app/media.py pyproject.toml uv.lock tests/test_core.py
git commit -m "$(cat <<'EOF'
fix: chan vong lap vo han khi doc WAV bi cat do

Header WAV khai nhieu frame hon du lieu thuc (ffmpeg bi kill giua chung)
khien readframes tra ve rong va pos khong tien -> treo vinh vien, an 100% CPU.
Vi server chi cho 1 job, moi job sau do deu bi 409.

Them pytest-timeout de test loai nay fail thay vi treo ca suite.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Timeout cho ffmpeg

`_run_ffmpeg` gọi `subprocess.run` không có `timeout`, trong khi `duration_seconds` (ffprobe, dòng 40) thì có. ffmpeg treo trên một file hỏng → job treo → 409 vĩnh viễn, cùng hệ quả với Task 1.

**Files:**
- Modify: `app/media.py:51-55`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có.
- Produces: `_run_ffmpeg(args: list[str]) -> None` — nay raise `RuntimeError` (thay vì treo) khi quá `_FFMPEG_TIMEOUT`. `extract_audio` và `to_wav16k` gọi qua nó nên tự hưởng hành vi mới; `extract_audio` bắt `RuntimeError` để fallback sang encode AAC, nên timeout ở nhánh copy sẽ khiến nó thử lại bằng AAC — chấp nhận được.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`:

```python
def test_run_ffmpeg_raises_on_timeout(monkeypatch):
    from app import media

    def fake_run(cmd, **kwargs):
        assert kwargs.get("timeout") == media._FFMPEG_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    monkeypatch.setattr(media, "ffmpeg_path", lambda: "ffmpeg")

    with pytest.raises(RuntimeError, match="quá"):
        media._run_ffmpeg(["-i", "x.wav", "y.wav"])
```

Thêm `import subprocess` vào khối import đầu `tests/test_core.py` nếu chưa có.

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py::test_run_ffmpeg_raises_on_timeout -v`

Expected: FAIL với `AttributeError: module 'app.media' has no attribute '_FFMPEG_TIMEOUT'`

- [ ] **Step 3: Thêm timeout**

Trong `app/media.py`, thay `_run_ffmpeg` bằng:

```python
# 1 giờ: dư cho file 4h convert trên CPU yếu, nhưng chặn được ffmpeg treo vĩnh viễn.
_FFMPEG_TIMEOUT = 3600


def _run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_path(), "-hide_banner", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ffmpeg chạy quá {_FFMPEG_TIMEOUT // 60} phút mà chưa xong — đã dừng. "
            "File có thể bị hỏng."
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {proc.stderr[-2000:]}")
```

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `uv run pytest tests/test_core.py -q`

Expected: toàn bộ pass.

- [ ] **Step 5: Lint và commit**

```bash
uv run ruff check .
git add app/media.py tests/test_core.py
git commit -m "$(cat <<'EOF'
fix: them timeout cho ffmpeg de job khong treo vinh vien

ffprobe da co timeout, ffmpeg thi khong. ffmpeg treo -> job treo ->
server 409 moi job sau do.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Xóa job đã kết thúc khỏi RAM

`_get_job` có comment (server.py:315) nói rõ *không* cache job đã kết thúc vào RAM vì mỗi job mang theo toàn bộ transcript. Nhưng `_run_job` lại ghi `result` thẳng vào `JOBS` và không có gì xóa nó ra — ý định trong comment và hành vi thực tế ngược nhau. RAM phình dần theo số job trong một phiên; với file 3 giờ mỗi transcript là vài chục MB.

Thứ tự bắt buộc: **ghi đĩa trước, pop khỏi RAM sau** — nếu pop trước, client đang poll sẽ nhận 404.

**Files:**
- Modify: `app/server.py:167-189`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có.
- Produces: `_run_job(job_id: str, input_path: Path, opts: dict) -> None` — sau khi chạy xong (cả nhánh thành công lẫn nhánh lỗi), `job_id` **không còn** trong `server.JOBS`; nguồn chân lý là `status.json`. `_get_job(job_id)` vẫn trả đúng như cũ vì nó tự đọc đĩa.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`:

```python
def test_finished_job_is_evicted_from_memory(monkeypatch, tmp_path):
    from app import config, pipeline, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: {
        "sentences": [{"start": 0.0, "end": 1.0, "text": "xin chào", "speaker": None}],
        "duration": 1.0,
        "num_speakers": 0,
        "extracted_audio": None,
        "model": "phowhisper-small",
        "punctuation": {"requested": False, "applied": False, "warning": None},
    })
    server.JOBS.clear()
    server.JOBS["j1"] = {"status": "running", "filename": "a.wav", "model": "phowhisper-small"}

    server._run_job("j1", tmp_path / "a.wav", {
        "model": "phowhisper-small", "language": "vi", "diarize": False,
        "punctuate": False, "num_speakers": 0, "glossary": "",
    })

    assert "j1" not in server.JOBS          # không giữ transcript trong RAM
    assert server._get_job("j1")["status"] == "done"   # vẫn đọc được từ đĩa


def test_failed_job_is_also_evicted_from_memory(monkeypatch, tmp_path):
    from app import config, pipeline, server

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    def boom(*a, **k):
        raise RuntimeError("ffmpeg lỗi")

    monkeypatch.setattr(pipeline, "run", boom)
    server.JOBS.clear()
    server.JOBS["j2"] = {"status": "running", "filename": "b.wav", "model": "phowhisper-small"}

    server._run_job("j2", tmp_path / "b.wav", {
        "model": "phowhisper-small", "language": "vi", "diarize": False,
        "punctuate": False, "num_speakers": 0, "glossary": "",
    })

    # Quan trọng: job lỗi cũng phải rời RAM, nếu không nó chặn mọi job sau bằng 409
    assert "j2" not in server.JOBS
    assert server._get_job("j2")["status"] == "error"
```

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py -k evicted -v`

Expected: cả 2 FAIL với `assert 'j1' not in {...}` / `assert 'j2' not in {...}`

- [ ] **Step 3: Xóa job khỏi RAM sau khi ghi đĩa**

Trong `app/server.py`, nhánh thành công của `_run_job`, sau `_save_job(job_id, snap)`:

```python
        _save_job(job_id, snap)
        # Kết quả đã nằm trên đĩa. Giữ tiếp trong RAM sẽ phình dần theo số job
        # (mỗi job mang cả transcript) — _get_job tự đọc lại từ status.json.
        with _JOBS_LOCK:
            JOBS.pop(job_id, None)
        log.info(
            "Job %s xong: %d câu, %.0fs",
            job_id,
            len(result.get("sentences") or []),
            result.get("duration") or 0,
        )
```

Và nhánh `except`, sau `_save_job(job_id, snap)`:

```python
        _save_job(job_id, snap)
        with _JOBS_LOCK:
            JOBS.pop(job_id, None)
```

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `uv run pytest tests/test_core.py -q`

Expected: toàn bộ pass.

- [ ] **Step 5: Lint và commit**

```bash
uv run ruff check .
git add app/server.py tests/test_core.py
git commit -m "$(cat <<'EOF'
fix: xoa job da ket thuc khoi RAM

Comment o _get_job noi ro khong cache job da xong vao RAM vi moi job mang
ca transcript, nhung _run_job van ghi result thang vao JOBS va khong ai xoa.
Ghi dia truoc, pop sau — de client dang poll khong nhan 404.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Kiểm tra toàn vẹn và timeout khi tải model diarization

`diarize._download` dùng `urlretrieve` rồi dùng thẳng file: không checksum, không timeout. So với `punctuate._ensure_model_dir` — pin revision, check size, check SHA-256, ghi manifest atomic — thì cùng một repo đang có hai chuẩn an toàn khác hẳn nhau. Không timeout nghĩa là mạng treo giữa chừng thì job đứng im vô thời hạn, người dùng chỉ thấy "Đang phân biệt người nói… 0%".

Task này cũng gom `_sha256` (đang nằm riêng trong `punctuate.py`) thành `config.sha256_file` dùng chung.

**Lưu ý trung thực:** hash được chốt bằng cách tải một lần rồi ghi lại (trust-on-first-use). Nó bảo vệ được lỗi tải dở, proxy chèn nội dung, và việc upstream lặng lẽ thay file — nhưng không chứng minh được bản đầu tiên là sạch.

**Files:**
- Modify: `app/config.py` (thêm `sha256_file`)
- Modify: `app/punctuate.py:39-44, 61` (dùng helper chung)
- Modify: `app/diarize.py:14-22, 41-64`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `config.sha256_file(path: Path) -> str` — SHA-256 hex, đọc theo khối 1 MB.
  - `diarize._download(url: str, dest: Path, sha256: str) -> None` — thêm tham số thứ 3 bắt buộc; raise `RuntimeError` nếu hash lệch, xóa file `.part`.
  - `diarize._SEG_SHA256`, `diarize._EMB_SHA256`, `diarize._DOWNLOAD_TIMEOUT` — hằng module.
  - `diarize.ensure_models() -> tuple[Path, Path]` — chữ ký không đổi.

- [ ] **Step 1: Lấy SHA-256 thật của 2 file model**

Chạy (tải ~30 MB, mất 1–3 phút):

```bash
uv run python -c "
import hashlib, urllib.request
urls = {
    'SEG': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2',
    'EMB': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx',
}
for name, url in urls.items():
    d = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=300) as r:
        while (c := r.read(1 << 20)):
            d.update(c)
    print(name, d.hexdigest())
"
```

Ghi lại 2 chuỗi hex in ra — dùng ở Step 4.

- [ ] **Step 2: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`:

```python
def test_sha256_file_matches_hashlib(tmp_path):
    import hashlib

    from app import config

    p = tmp_path / "x.bin"
    p.write_bytes(b"vitranscript" * 1000)
    assert config.sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_download_rejects_wrong_hash(tmp_path, monkeypatch):
    import io

    from app import diarize

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        diarize.urllib.request, "urlopen", lambda url, timeout: FakeResponse(b"noi dung sai")
    )
    dest = tmp_path / "model.onnx"

    with pytest.raises(RuntimeError, match="SHA-256"):
        diarize._download("https://example.invalid/m.onnx", dest, "0" * 64)

    assert not dest.exists()                              # không để lại file hỏng
    assert not dest.with_suffix(".onnx.part").exists()    # dọn cả file tạm


def test_download_accepts_matching_hash(tmp_path, monkeypatch):
    import hashlib
    import io

    from app import diarize

    payload = b"noi dung dung"

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        diarize.urllib.request, "urlopen", lambda url, timeout: FakeResponse(payload)
    )
    dest = tmp_path / "model.onnx"

    diarize._download("https://example.invalid/m.onnx", dest, hashlib.sha256(payload).hexdigest())

    assert dest.read_bytes() == payload
```

- [ ] **Step 3: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py -k "sha256_file or download_" -v`

Expected: FAIL — `AttributeError: module 'app.config' has no attribute 'sha256_file'` và `_download() takes 2 positional arguments but 3 were given`

- [ ] **Step 4: Thêm helper chung và siết `_download`**

Trong `app/config.py`, thêm `import hashlib` vào khối import đầu file, và thêm hàm (đặt ngay trên `def data_dir()`):

```python
def sha256_file(path: Path) -> str:
    """SHA-256 của file, đọc theo khối 1 MB (model có thể vài trăm MB)."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
```

Trong `app/punctuate.py`: xóa hàm `_sha256` (dòng 39-44) và `import hashlib`, rồi đổi chỗ dùng ở dòng 61:

```python
    actual_hash = config.sha256_file(model_path)
```

Trong `app/diarize.py`, thay hằng và `_download`:

```python
# Hash chốt bằng cách tải một lần rồi ghi lại (trust-on-first-use): bắt được
# tải dở, proxy chèn nội dung, và việc upstream lặng lẽ thay file.
_SEG_SHA256 = "<dán hex SEG từ Step 1>"
_EMB_SHA256 = "<dán hex EMB từ Step 1>"
_DOWNLOAD_TIMEOUT = 300  # giây, cho mỗi thao tác đọc socket


def _download(url: str, dest: Path, sha256: str) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as resp, tmp.open("wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    actual = config.sha256_file(tmp)
    if actual != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Model diarization tải về sai SHA-256 (nhận {actual[:12]}…). "
            "Hãy thử lại; nếu vẫn lỗi thì nguồn tải đã thay đổi."
        )
    tmp.rename(dest)
```

Và cập nhật 2 chỗ gọi trong `ensure_models`:

```python
        _download(_SEG_URL, archive, _SEG_SHA256)
```

```python
        _download(_EMB_URL, emb_model, _EMB_SHA256)
```

- [ ] **Step 5: Chạy test để xác nhận pass**

Run: `uv run pytest tests/ -q`

Expected: toàn bộ pass.

- [ ] **Step 6: Kiểm tra tải thật đầu-cuối**

Xóa cache diarization rồi chạy lại để chắc hash đã pin là đúng:

```bash
rm -rf "$HOME/Library/Application Support/ViTranscript/diarization"
uv run python -c "from app.diarize import ensure_models; print(ensure_models())"
```

Expected: in ra 2 đường dẫn tồn tại, không raise. Nếu raise "sai SHA-256" → hex ở Step 4 dán nhầm.

- [ ] **Step 7: Lint và commit**

```bash
uv run ruff check .
git add app/config.py app/punctuate.py app/diarize.py tests/test_core.py
git commit -m "$(cat <<'EOF'
fix: kiem tra SHA-256 va them timeout khi tai model diarization

Nhanh punctuate da pin revision + check hash + manifest atomic, nhanh
diarize thi urlretrieve roi dung thang. Gom _sha256 thanh config.sha256_file
dung chung cho ca hai.

Hash chot theo kieu trust-on-first-use: bat duoc tai do / proxy chen noi dung
/ upstream thay file, nhung khong chung minh ban dau tien la sach.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Phục hồi dấu câu hỏng theo chunk, không hỏng cả file

`_encode_chunk` dựng `offsets = [first_subword[position] ...]` sẽ `KeyError` nếu tokenizer nuốt trọn một token (ký tự điều khiển, một số ký tự unicode). `restore` bắt `Exception` rất rộng nên không crash — nhưng hậu quả là **toàn bộ transcript mất dấu câu chỉ vì một từ**. Phạm vi hỏng nên là chunk (48 từ) chứ không phải cả file.

`_choose_overlapping` đã mặc định `$KEEP` cho mọi vị trí, nên chunk bị bỏ qua sẽ tự giữ nguyên văn bản gốc; các chunk kề bên còn phủ chồng lấn nên phần lớn vị trí vẫn có dự đoán.

**Files:**
- Modify: `app/punctuate.py:288-306` (`_predict_actions`), `309-347` (`restore`)
- Test: `tests/test_punctuate.py`

**Interfaces:**
- Consumes: `config.sha256_file` (Task 4) — không dùng trực tiếp ở task này.
- Produces:
  - `_predict_actions(pieces, runtime, progress_cb=None) -> tuple[list[str], int]` — **đổi kiểu trả về**: nay là `(actions, so_chunk_loi)`. Raise `RuntimeError` nếu *mọi* chunk đều lỗi (giữ nguyên hành vi fallback cả file cho trường hợp model hỏng thật).
  - `restore(...) -> PunctuationResult` — chữ ký không đổi. Khi có chunk lỗi nhưng không phải tất cả: `applied=True`, `warning` là chuỗi `_PARTIAL_WARNING`.
  - `_PARTIAL_WARNING: str` — hằng module.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_punctuate.py`:

```python
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
```

Thêm `import pytest` vào đầu `tests/test_punctuate.py` nếu chưa có.

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_punctuate.py -k predict_actions_skips -v`

Expected: FAIL với `KeyError: 'token bi tokenizer nuot'` (lỗi thoát ra ngoài thay vì bị nuốt theo chunk).

- [ ] **Step 3: Bắt lỗi theo từng chunk**

Trong `app/punctuate.py`, thay `_predict_actions`:

```python
def _predict_actions(
    pieces: list[_Piece],
    runtime: _Runtime,
    progress_cb: Callable[[float], None] | None = None,
) -> tuple[list[str], int]:
    predictions = []
    furthest = 0
    failed = 0
    ranges = _chunk_ranges(len(pieces))
    for start, end in ranges:
        try:
            feeds = _encode_chunk(runtime, pieces[start:end])
            logits = runtime.session.run(["logits", "detect_logits"], feeds)[0]
            label_ids = np.argmax(logits[0], axis=-1).tolist()
            actions = [runtime.labels[index] for index in label_ids]
            if len(actions) != end - start:
                raise RuntimeError("Model dấu câu trả sai số word")
        except Exception:
            # Một chunk hỏng (ví dụ tokenizer nuốt trọn một token lạ) không được
            # làm mất dấu câu của cả file — _choose_overlapping mặc định $KEEP.
            log.exception("Bỏ qua chunk dấu câu %d-%d", start, end)
            failed += 1
            continue
        predictions.append((start, end, actions))
        furthest = max(furthest, end)
        if progress_cb:
            progress_cb(furthest / len(pieces))
    if ranges and failed == len(ranges):
        raise RuntimeError("Toàn bộ chunk dấu câu đều lỗi")
    return _choose_overlapping(len(pieces), predictions), failed
```

- [ ] **Step 4: Cập nhật `restore` cho khớp kiểu trả về mới**

Thêm hằng cạnh `_WARNING` (dòng 179):

```python
_PARTIAL_WARNING = (
    "Một số đoạn không phục hồi được dấu câu; các đoạn còn lại vẫn được xử lý."
)
```

Trong `restore`, thay vòng lặp 3 bước:

```python
        failed_chunks = 0
        for iteration in range(3):
            actions, failed = _predict_actions(
                pieces, runtime, monotonic if iteration == 0 else None
            )
            failed_chunks = max(failed_chunks, failed)
            changed = False
            for piece, action in zip(pieces, actions, strict=True):
                changed = _apply_safe_action(piece, action) or changed
            if not changed:
                break
        restored = _rebuild_words(original, layouts, pieces)
        if not _invariants_hold(original, restored):
            raise RuntimeError("Invariant punctuation bị vi phạm")
        if progress_cb:
            progress_cb(1.0)
        return PunctuationResult(
            restored, True, _PARTIAL_WARNING if failed_chunks else None
        )
```

- [ ] **Step 5: Chạy test để xác nhận pass**

Run: `uv run pytest tests/ -q`

Expected: toàn bộ pass. Đặc biệt các test cũ `test_restore_falls_back_whole_input_on_any_error` và `test_predict_actions_builds_word_offsets_for_onnx` phải vẫn xanh — nếu test sau fail vì kiểu trả về đổi, sửa nó thành `actions, _ = punctuate._predict_actions(...)`.

- [ ] **Step 6: Lint và commit**

```bash
uv run ruff check .
git add app/punctuate.py tests/test_punctuate.py
git commit -m "$(cat <<'EOF'
fix: chunk dau cau hong khong lam mat dau cau ca file

_encode_chunk KeyError khi tokenizer nuot tron mot token la; restore bat
Exception rat rong nen ca transcript mat dau cau chi vi mot tu. Nay bat loi
theo tung chunk, _choose_overlapping mac dinh $KEEP nen chunk hong giu nguyen
van ban goc. Van fallback ca file khi moi chunk deu loi.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Validate `names` từ client khi export

`export_job` nhận `names` từ request body không kiểm tra kiểu. Client gửi `{"0": 123}` → `speaker_name` gọi `.strip()` trên int → `AttributeError` → HTTP 500 thay vì 400.

**Files:**
- Modify: `app/server.py:327-338`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có.
- Produces: `_clean_names(raw) -> dict[str, str]` trong `app/server.py` — trả `{}` nếu `raw` không phải dict; bỏ qua entry có value không phải `str`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`:

```python
def test_clean_names_drops_non_string_values():
    from app.server import _clean_names

    assert _clean_names({"0": "Huy", "1": 123, "2": None}) == {"0": "Huy"}
    assert _clean_names(None) == {}
    assert _clean_names("khong phai dict") == {}
    assert _clean_names({0: "Huy"}) == {"0": "Huy"}  # key so -> chuoi
```

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py::test_clean_names_drops_non_string_values -v`

Expected: FAIL với `ImportError: cannot import name '_clean_names'`

- [ ] **Step 3: Thêm hàm và dùng nó**

Trong `app/server.py`, thêm ngay trên `def _status_path`:

```python
def _clean_names(raw) -> dict[str, str]:
    """names do client gửi: chỉ nhận map str→str. Entry sai kiểu bỏ qua êm,
    tránh AttributeError trong speaker_name làm export trả 500."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, str)}
```

Trong `export_job`, thay dòng `names = body.get("names") or {}`:

```python
    names = _clean_names(body.get("names"))
```

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `uv run pytest tests/test_core.py -q`

Expected: toàn bộ pass.

- [ ] **Step 5: Lint và commit**

```bash
uv run ruff check .
git add app/server.py tests/test_core.py
git commit -m "$(cat <<'EOF'
fix: validate names tu client khi export

names khong duoc kiem tra kieu; {"0": 123} lam speaker_name goi .strip()
tren int -> HTTP 500 thay vi bo qua entry sai.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Giải phóng model cũ trước khi nạp model mới

`load_model` gọi `_MODEL_CACHE.clear()` **sau** khi `WhisperModel` mới đã dựng xong, nên có khoảnh khắc cả model cũ lẫn mới cùng nằm trong RAM. Đổi từ PhoWhisper Large (~3 GB) sang model khác thì đỉnh RAM là tổng hai model — đúng vào tình huống máy CPU yếu mà comment ngay dưới đang muốn tránh.

**Files:**
- Modify: `app/transcribe.py:20-36`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: không có.
- Produces: `load_model(model_key: str)` — chữ ký và giá trị trả về không đổi; khác biệt là `_MODEL_CACHE` rỗng *trong lúc* `WhisperModel.__init__` chạy.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_core.py`:

```python
def test_load_model_frees_old_model_before_building_new(monkeypatch):
    import app.transcribe as tr

    seen_during_construct = {}

    class FakeWhisperModel:
        def __init__(self, source, **kwargs):
            # Model cu phai da bi giai phong TRUOC khi model moi cap phat RAM
            seen_during_construct["cache"] = dict(tr._MODEL_CACHE)

    fake_module = type("M", (), {"WhisperModel": FakeWhisperModel})
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_module)

    tr._MODEL_CACHE.clear()
    tr._MODEL_CACHE["phowhisper-large"] = object()
    tr.load_model("phowhisper-small")

    assert seen_during_construct["cache"] == {}
    assert list(tr._MODEL_CACHE) == ["phowhisper-small"]
    tr._MODEL_CACHE.clear()
```

- [ ] **Step 2: Chạy test để xác nhận nó fail**

Run: `uv run pytest tests/test_core.py::test_load_model_frees_old_model_before_building_new -v`

Expected: FAIL — `assert {'phowhisper-large': <object>} == {}`

- [ ] **Step 3: Đổi thứ tự**

Trong `app/transcribe.py`, thay thân `load_model` sau phần kiểm tra cache:

```python
    from faster_whisper import WhisperModel

    source = config.MODEL_REGISTRY[model_key]["source"]
    # Nhả model cũ TRƯỚC khi cấp phát model mới: nếu clear() sau, đỉnh RAM là
    # tổng hai model (đổi từ Large ~3GB sang model khác sẽ đội gấp đôi).
    _MODEL_CACHE.clear()
    model = WhisperModel(
        source,
        device="cpu",
        compute_type="int8",
        download_root=str(config.models_dir()),
    )
    _MODEL_CACHE[model_key] = model
    return model
```

- [ ] **Step 4: Chạy test để xác nhận pass**

Run: `uv run pytest tests/test_core.py -q`

Expected: toàn bộ pass.

- [ ] **Step 5: Lint và commit**

```bash
uv run ruff check .
git add app/transcribe.py tests/test_core.py
git commit -m "$(cat <<'EOF'
perf: nha model cu truoc khi cap phat model moi

clear() chay sau khi WhisperModel moi da dung xong -> dinh RAM la tong hai
model, dung vao tinh huong may CPU yeu ma comment ngay duoi dang muon tranh.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Dọn điều kiện thừa và đồng bộ tài liệu

`merge_minor_speakers` pass 2 có `elif new_spk[i] not in keep and next_kept is not None` — vế `not in keep` thừa vì `elif` đã hàm ý điều đó. Và `CLAUDE.md` / `AGENTS.md` đang ghi "expected: 8 passed" trong khi thực tế 46 test.

**Files:**
- Modify: `app/diarize.py:126-131`
- Modify: `CLAUDE.md` (worktree), `../../CLAUDE.md` và `../../AGENTS.md` (repo gốc)
- Test: không thêm test mới — `test_merge_minor_speakers_collapses_noise_ids` và `test_merge_minor_speakers_respects_max_speakers` đã phủ hành vi này.

**Interfaces:**
- Consumes: không có.
- Produces: không đổi interface nào.

- [ ] **Step 1: Chạy test hiện có để có mốc so sánh**

Run: `uv run pytest tests/test_core.py -k merge_minor -v`

Expected: 2 passed. Ghi lại để Step 3 đối chiếu.

- [ ] **Step 2: Bỏ vế thừa**

Trong `app/diarize.py`, pass 2:

```python
    # pass 2: backward fill for prefix that had no previous kept
    next_kept: int | None = None
    for i in range(n - 1, -1, -1):
        if new_spk[i] in keep:
            next_kept = new_spk[i]
        elif next_kept is not None:
            new_spk[i] = next_kept
```

- [ ] **Step 3: Chạy lại test để xác nhận hành vi không đổi**

Run: `uv run pytest tests/ -q`

Expected: cùng số test pass như baseline (46 + các test thêm ở Task 1–7).

- [ ] **Step 4: Sửa số test trong tài liệu**

Trong `CLAUDE.md` của worktree, mục "Lệnh nhanh":

```
uv run pytest tests/ -v           # unit tests — expected: 46 passed, 1 deselected
```

Trong `CLAUDE.md` và `AGENTS.md` của repo gốc (`/Users/huytv/Github/cba_Transcript_local`), sửa dòng task 8 trong bảng trạng thái từ `(tests/test_core.py, 8 test)` / `8 test pass` thành số thật sau khi chạy `uv run pytest tests/ -q`. Cập nhật cả block `<!-- auto-update: start -->` trong `CLAUDE.md` và `<!-- status-block: start -->` trong `AGENTS.md` cho khớp nhau, đúng RULE trong CLAUDE.md.

- [ ] **Step 5: Lint và commit**

```bash
uv run ruff check .
git add app/diarize.py CLAUDE.md
git commit -m "$(cat <<'EOF'
chore: bo dieu kien thua trong merge_minor_speakers, sua so test trong doc

elif da ham y "not in keep". Doc ghi 8 test trong khi thuc te 46.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

Commit `CLAUDE.md` + `AGENTS.md` của repo gốc riêng (khác branch):

```bash
cd /Users/huytv/Github/cba_Transcript_local
git add CLAUDE.md AGENTS.md
git commit -m "$(cat <<'EOF'
docs: sua so unit test (8 -> so thuc te)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Cố ý KHÔNG làm trong plan này

Ba mục xuất hiện trong review nhưng bị loại sau khi cân nhắc — ghi lại lý do để lần sau không phải suy nghĩ lại:

**1. Escape công thức khi xuất XLSX.** Text bắt đầu bằng `=` `+` `-` `@` bị Excel hiểu là công thức. Nhưng đây là app local-first: "kẻ tấn công" chính là file audio của người dùng. Trong khi đó transcript tiếng Việt bắt đầu bằng `-` (gạch đầu dòng hội thoại) là chuyện thường, và thêm dấu `'` sẽ lọt vào giá trị ô khi đọc lại bằng openpyxl. Cái giá chắc chắn lớn hơn rủi ro giả định.

**2. Giảm số vòng lặp inference dấu câu (`for iteration in range(3)`).** Nghi ngờ là các case action dao động (CAPITAL → LOWER → CAPITAL) khiến `changed` luôn True và luôn tốn đủ 3 lần inference. Nhưng đây là câu hỏi **đo được**, và chưa có `eval/sample.*` để đo. Sửa mù sẽ đánh đổi chất lượng dấu câu lấy tốc độ mà không biết tỷ giá. Việc cần làm trước là task 12b (người dùng cung cấp file audio thật) — sau đó mới đo vòng 2 và 3 có đổi gì không.

**3. Tự động dọn thư mục `jobs/`.** Đã có trong danh sách rủi ro của CLAUDE.md với quyết định "v1: xóa thủ công". Không thay đổi quyết định đó trong plan sửa lỗi.

## Thứ tự đề xuất và điểm dừng

Task 1–3 nên đi cùng nhau: cả ba đều dẫn tới cùng một triệu chứng người dùng thấy — "app đứng im, bấm gì cũng báo đang có job chạy". Sau Task 3 là điểm dừng tự nhiên nếu muốn kiểm chứng bằng tay trước khi đi tiếp.

Task 4 cần mạng và mất vài phút tải. Task 5 là thay đổi tinh vi nhất, nên làm khi còn tỉnh táo. Task 6–8 nhỏ, gộp vào một phiên cũng được.
