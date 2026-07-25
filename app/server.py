"""Web server local: FastAPI + job chạy nền trong thread. Chạy: python -m app.server"""
import json
import logging
import socket
import threading
import time
import traceback
import uuid
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import checkpoint, config, export, media, pipeline, segment
from .segment import Sentence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("vitranscript")

app = FastAPI(title="ViTranscript")
JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_STATIC = Path(__file__).parent / "static"
_EXPORTERS = {
    "docx": export.to_docx,
    "xlsx": export.to_xlsx,
    "srt": export.to_srt,
    "txt": export.to_txt,
}
# 1x1 transparent PNG — tránh 404 favicon làm nhiễu console
_FAVICON = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

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
            "Hãy cắt file thành các phần ngắn hơn "
            "(ví dụ bằng QuickTime/ffmpeg) rồi chạy từng phần.",
        )
    if diarize and duration > _MAX_DIARIZE_SECONDS:
        return False, (
            f"File dài {duration / 3600:.1f} giờ nên đã tự tắt phân biệt người nói "
            "để tránh hết bộ nhớ. Transcript và timestamp vẫn đầy đủ."
        )
    return diarize, None


def _apply_speaker_overrides(sentences: list[Sentence], overrides: dict | None) -> None:
    """Áp chỉnh sửa người nói từ client (best-effort, entry không hợp lệ bỏ qua êm)."""
    if not overrides:
        return
    valid = {s.speaker for s in sentences if s.speaker is not None}
    for k, v in overrides.items():
        try:
            i, spk = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(sentences) and spk in valid and sentences[i].speaker is not None:
            sentences[i].speaker = spk


def _clean_names(raw) -> dict[str, str]:
    """names do client gửi: chỉ nhận map str→str. Entry sai kiểu bỏ qua êm,
    tránh AttributeError trong speaker_name làm export trả 500."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, str)}


def _status_path(job_id: str) -> Path:
    return config.jobs_dir() / job_id / "status.json"


def _save_job(job_id: str, job: dict) -> bool:
    """Ghi trạng thái job ra đĩa (để UI không mất hết nếu process bị kill).

    Trả về True nếu ghi thành công, False nếu thất bại — caller (_run_job) dùng
    giá trị này để quyết định có được phép bỏ job khỏi RAM hay không: nếu đĩa
    ghi lỗi thì RAM là nơi duy nhất còn giữ kết quả.
    """
    path = _status_path(job_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Không ghi result khổng lồ quá thường xuyên — luôn ghi khi done/error
        path.write_text(json.dumps(job, ensure_ascii=False, default=str), encoding="utf-8")
        return True
    except OSError as e:
        log.warning("Không ghi được status job %s: %s", job_id, e)
        return False


def _load_job_from_disk(job_id: str) -> dict | None:
    path = _status_path(job_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(content=_FAVICON, media_type="image/png")


@app.get("/api/meta")
def meta():
    return {
        "models": [
            {
                "key": k,
                "label": v["label"],
                "size": v["size"],
                "downloaded": config.model_is_downloaded(k),
            }
            for k, v in config.MODEL_REGISTRY.items()
        ],
        "settings": config.load_settings(),
        "glossary": config.load_glossary_text(),
        "punctuation": {
            "downloaded": config.punctuation_is_downloaded(),
            "size": "~110 MB",
            "license": config.PUNCTUATION_MODEL["license"],
        },
    }


def _run_job(job_id: str, input_path: Path, opts: dict) -> None:
    last_save = 0.0

    def progress(stage: str, pct: float, msg: str):
        nonlocal last_save
        with _JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job.update(stage=stage, percent=round(pct, 1), message=msg)
            snap = dict(job)
        # Throttle ghi đĩa: tối đa ~2 lần/giây (diarize callback rất dày)
        now = time.monotonic()
        if now - last_save >= 0.5 or pct >= 100:
            last_save = now
            _save_job(job_id, snap)

    try:
        log.info("Job %s bắt đầu: %s model=%s", job_id, input_path.name, opts["model"])
        result = pipeline.run(
            input_path,
            input_path.parent,
            opts["model"],
            language=opts["language"],
            enable_punctuation=opts["punctuate"],
            enable_diarization=opts["diarize"],
            num_speakers=opts["num_speakers"],
            glossary_text=opts["glossary"],
            progress=progress,
        )
        with _JOBS_LOCK:
            job = JOBS[job_id]
            warning = (result.get("punctuation") or {}).get("warning")
            if warning:
                existing = str(job.get("note") or "").strip()
                job["note"] = "\n".join(part for part in (existing, warning) if part)
            job.update(status="done", result=result, percent=100, message="Hoàn tất!")
            snap = dict(job)
        saved = _save_job(job_id, snap)
        # Kết quả đã nằm trên đĩa. Giữ tiếp trong RAM sẽ phình dần theo số job
        # (mỗi job mang cả transcript) — _get_job tự đọc lại từ status.json.
        # Nếu ghi đĩa thất bại thì RAM là nơi duy nhất còn giữ kết quả — PHẢI
        # giữ lại job trong JOBS (status đã là "done" ở trên, không phải "running",
        # nên không ảnh hưởng kiểm tra 409 trong create_job).
        if saved:
            with _JOBS_LOCK:
                JOBS.pop(job_id, None)
        log.info(
            "Job %s xong: %d câu, %.0fs",
            job_id,
            len(result.get("sentences") or []),
            result.get("duration") or 0,
        )
    except Exception as e:
        log.error("Job %s lỗi: %s\n%s", job_id, e, traceback.format_exc())
        with _JOBS_LOCK:
            job = JOBS.get(job_id, {})
            job.update(status="error", message=f"Lỗi: {e}", percent=100)
            JOBS[job_id] = job
            snap = dict(job)
        saved = _save_job(job_id, snap)
        # Cùng lý do như nhánh thành công: chỉ nhả RAM khi đĩa đã có bản ghi
        # thay thế. status đã là "error", không phải "running".
        if saved:
            with _JOBS_LOCK:
                JOBS.pop(job_id, None)


@app.post("/api/jobs")
async def create_job(
    file: Annotated[UploadFile, File()],
    model: Annotated[str, Form()],
    language: Annotated[str, Form()] = "vi",
    diarize: Annotated[bool, Form()] = True,
    punctuate: Annotated[bool, Form()] = True,
    num_speakers: Annotated[int, Form()] = 0,
    glossary: Annotated[str, Form()] = "",
):
    if model not in config.MODEL_REGISTRY:
        raise HTTPException(400, "Model không hợp lệ")
    name = Path(file.filename or "input")
    if not media.is_supported(name):
        raise HTTPException(400, f"Định dạng {name.suffix} chưa hỗ trợ")

    job_id = uuid.uuid4().hex[:12]
    job = {
        "status": "running",
        "stage": "queued",
        "percent": 0,
        "message": "Đang chuẩn bị…",
        "filename": name.name,
        "model": model,
        "punctuate": punctuate,
    }
    # Đặt chỗ nguyên tử: kiểm tra "đang chạy" và ghi job trong cùng một lần giữ lock,
    # tránh hai request cùng lọt qua kiểm tra rồi cùng khởi chạy.
    with _JOBS_LOCK:
        if any(j.get("status") == "running" for j in JOBS.values()):
            raise HTTPException(
                409,
                "Đang có job khác chạy. Vui lòng đợi xong rồi thử lại.",
            )
        JOBS[job_id] = job
    _save_job(job_id, job)

    # Nếu chuẩn bị file thất bại, phải nhả chỗ đã đặt — nếu không job "running"
    # sẽ kẹt vĩnh viễn và chặn mọi job sau.
    try:
        job_dir = config.jobs_dir() / job_id
        # _save_job ở trên đã tạo thư mục (ghi status.json) — exist_ok tránh FileExistsError 500
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / ("input" + name.suffix.lower())
        with input_path.open("wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)

        duration = media.duration_seconds(input_path)
        diarize, note = _long_audio_policy(duration, diarize)
        if note:
            with _JOBS_LOCK:
                JOBS[job_id]["note"] = note
            _save_job(job_id, JOBS[job_id])

        config.save_settings({
            "model": model, "language": language, "punctuate": punctuate,
        })
        config.save_glossary_text(glossary)

        opts = {
            "model": model,
            "language": language,
            "diarize": diarize,
            "punctuate": punctuate,
            "num_speakers": num_speakers,
            "glossary": glossary,
        }
        # daemon: khi process bị tắt (Ctrl+C) thì job dừng theo, không giữ interpreter
        # sống chờ transcript dài xong. Job dở dang được _get_job phục hồi từ disk.
        # Tạo + start thread nằm trong try: nếu Thread.start() ném RuntimeError
        # (vd không tạo được thread mới), chỗ đã đặt cũng phải được nhả — nếu
        # không job "running" kẹt vĩnh viễn và mọi job sau đều nhận 409.
        t = threading.Thread(target=_run_job, args=(job_id, input_path, opts), daemon=True)
        t.start()
    except Exception:
        with _JOBS_LOCK:
            JOBS.pop(job_id, None)
        raise
    return {"job_id": job_id}


def _get_job(job_id: str) -> dict:
    with _JOBS_LOCK:
        if job_id in JOBS:
            return dict(JOBS[job_id])
    disk = _load_job_from_disk(job_id)
    if disk:
        # Job từ lần chạy trước: nếu còn "running" thì process cũ đã chết
        if disk.get("status") == "running":
            disk["status"] = "error"
            disk["percent"] = 100
            words = checkpoint.load_words(_status_path(job_id).parent / "partial.jsonl")
            if words:
                sentences = segment.build_sentences(words)
                disk["partial"] = True
                punct_warning = "Bản khôi phục chưa được phục hồi dấu câu."
                disk["result"] = {
                    "sentences": [asdict(s) for s in sentences],
                    "duration": words[-1].end,
                    "num_speakers": 0,
                    "extracted_audio": None,
                    "model": disk.get("model", "?"),
                    "punctuation": {
                        "requested": bool(disk.get("punctuate", True)),
                        "applied": False,
                        "backend": "vibert-capu-onnx-int8",
                        "warning": punct_warning,
                    },
                }
                existing_note = str(disk.get("note") or "").strip()
                disk["note"] = "\n".join(
                    part for part in (existing_note, punct_warning) if part
                )
                disk["message"] = (
                    "Server đã dừng giữa chừng — nhưng phần transcript làm xong "
                    f"({len(sentences)} câu, tới phút {words[-1].end / 60:.0f}) "
                    "đã được khôi phục bên dưới. "
                    "Chạy lại file để có bản đầy đủ."
                )
            else:
                disk["message"] = (
                    "Server đã dừng giữa chừng (process bị tắt). "
                    "Hãy bấm Bắt đầu lại — model đã tải sẵn nên lần sau nhanh hơn."
                )
            _save_job(job_id, disk)
        # Không cache job đã kết thúc vào RAM: mỗi job "done" mang theo toàn bộ
        # transcript, cache lại sẽ phình bộ nhớ dần theo số lần truy vấn lịch sử.
        # Nguồn chân lý vẫn là status.json trên đĩa.
        return disk
    raise HTTPException(404, "Không tìm thấy job")


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _get_job(job_id)


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, body: dict):
    job = _get_job(job_id)
    if not (job.get("result") or {}).get("sentences"):
        raise HTTPException(409, "Job chưa xong")
    fmt = body.get("format", "docx")
    if fmt not in _EXPORTERS:
        raise HTTPException(400, "Định dạng không hợp lệ")
    names = _clean_names(body.get("names"))
    sentences = [Sentence(**s) for s in job["result"]["sentences"]]
    _apply_speaker_overrides(sentences, body.get("speakers"))
    stem = Path(job["filename"]).stem
    out = config.jobs_dir() / job_id / f"{stem}.{fmt}"
    if fmt == "docx":
        export.to_docx(
            sentences,
            out,
            f"Transcript — {job['filename']}",
            names,
            {
                "Model": job["result"]["model"],
                "Thời lượng": f"{job['result']['duration']:.0f}s",
            },
        )
    else:
        _EXPORTERS[fmt](sentences, out, names)
    return FileResponse(out, filename=out.name)


@app.get("/api/jobs/{job_id}/audio")
def download_audio(job_id: str):
    job = _get_job(job_id)
    extracted = (job.get("result") or {}).get("extracted_audio")
    if not extracted or not Path(extracted).exists():
        raise HTTPException(
            404, "Không có file audio tách riêng (đầu vào không phải video)"
        )
    p = Path(extracted)
    return FileResponse(p, filename=Path(job["filename"]).stem + p.suffix)


def _free_port(start: int = 8756) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Không tìm được port trống")


def main() -> None:
    port = _free_port()
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"\n  ViTranscript đang chạy tại http://127.0.0.1:{port}  (Ctrl+C để thoát)\n")
    # log_level info để thấy job start/end khi debug
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
