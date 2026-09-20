"""Web server local: FastAPI + job chạy nền trong thread. Chạy: python -m app.server"""
import json
import logging
import os
import re
import socket
import threading
import time
import traceback
import uuid
import webbrowser
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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
# Đủ cho video 4 giờ bitrate cao (~4,4 Mbps); chặn upload stream vô hạn làm đầy đĩa.
_MAX_UPLOAD_BYTES = 8 * 1024**3
_MAX_JSON_BODY = 4 * 1024**2  # export body chỉ chứa names/speakers — vài chục KB là đủ
_MAX_GLOSSARY_CHARS = 100_000
_MAX_FILENAME_CHARS = 200
_MAX_SPEAKERS = 20  # khớp max của UI; chặn số cực lớn đẩy vào thư viện clustering native
_JOB_ID_RE = re.compile(r"[0-9a-f]{12}")
_LANGUAGE_RE = re.compile(r"[a-z]{2,3}|auto")
_ALLOWED_HOSTS = {"127.0.0.1", "::1", "0.0.0.0", "localhost"}
# Ký tự cấm trong tên file Windows + ký tự điều khiển — filename do client gửi
# đi vào tên file export nên phải lọc trước khi ghép vào đường dẫn.
_UNSAFE_STEM_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Tên thiết bị Windows: cấm đặt tên file kể cả khi kèm đuôi mở rộng ("CON.docx"
# mở device thay vì tạo file). POSIX không cấm nên chỉ lộ trên Windows thật.
# Dạng superscript (U+00B9/B2/B3): Windows map ¹²³ → 1/2/3 nên COM¹ ≡ COM1.
_WIN_DEVICE_STEMS = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
    + ["COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"]
)
_SENTENCE_FIELDS = frozenset(("start", "end", "text", "speaker"))


def _security_headers(response: Response, path: str) -> Response:
    """Gắn security headers lên response. Phải gọi cho CẢ response từ chối sớm
    của middleware (403/411/413) lẫn response route trả về — nếu chỉ gắn sau
    call_next thì các trang lỗi sớm thiếu nosniff/CSP/no-store."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # transcript không nằm trong disk cache
    return response


@app.middleware("http")
async def _security_guard(request: Request, call_next):
    def deny(message: str, status: int) -> Response:
        return _security_headers(Response(message, status_code=status), request.url.path)

    # Host phải là loopback — chặn DNS rebinding: domain của kẻ tấn công resolve
    # về 127.0.0.1 vẫn bị từ chối vì trình duyệt giữ nguyên Host của domain đó.
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").rstrip(".")
    if host not in _ALLOWED_HOSTS:
        return deny("Chỉ chấp nhận truy cập từ máy local.", 403)
    # Request ghi (POST…) từ website khác bị chặn — chống CSRF: trang độc không
    # thể sai khiến trình duyệt upload file hay gọi export. Origin phải trùng
    # ĐÚNG origin của server (scheme+host+port): UI được phục vụ same-origin
    # nên request thật luôn khớp. Origin "null" (sandboxed iframe, file://,
    # redirect), origin không parse được, hay loopback khác port (trang độc
    # trên :9000 ghi sang :8756 vẫn là cross-origin theo browser) đều bị từ
    # chối. Client không gửi Origin (curl, script tự viết) vẫn chạy.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return deny("Origin không hợp lệ.", 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return deny("Request cross-site bị chặn.", 403)
        # Cap upload TRƯỚC khi Starlette parse multipart: request chunked không
        # Content-Length trước đây được spool hết vào SpooledTemporaryFile (đĩa)
        # trước khi endpoint chạy → lỗ hổng làm đầy đĩa. Browser/curl/httpx
        # luôn gửi Content-Length trên upload nên 411 không ảnh hưởng client
        # thật. Check trong create_job vẫn giữ nguyên (defense in depth — nó
        # còn bắt cả Content-Length khai thiếu so với body thực).
        if request.method in ("POST", "PUT", "PATCH") and request.url.path == "/api/jobs":
            content_length = request.headers.get("content-length")
            if content_length is None:
                return deny("Thiếu Content-Length.", 411)
            try:
                oversized = int(content_length) > _MAX_UPLOAD_BYTES
            except ValueError:
                oversized = True  # Content-Length không phải số → coi như quá lớn
            if oversized:
                return deny(
                    f"File lớn hơn {_MAX_UPLOAD_BYTES // (1 << 30)} GB — "
                    "hãy nén hoặc cắt file rồi thử lại.",
                    413,
                )
    response = await call_next(request)
    return _security_headers(response, request.url.path)


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


def _job_dir(job_id: str) -> Path:
    """Thư mục của job — chỉ chấp nhận id đúng định dạng uuid-hex-12 do server tự sinh.

    job_id đi từ URL path vào đường dẫn file: giá trị như ".." hay "a\\b" (trên
    Windows) sẽ thoát ra ngoài jobs/ nếu không lọc → path traversal đọc/ghi.
    """
    if not _JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(404, "Không tìm thấy job")
    return config.jobs_dir() / job_id


def _status_path(job_id: str) -> Path:
    return _job_dir(job_id) / "status.json"


def _save_job(job_id: str, job: dict) -> bool:
    """Ghi trạng thái job ra đĩa (để UI không mất hết nếu process bị kill).

    Trả về True nếu ghi thành công, False nếu thất bại — caller (_run_job) dùng
    giá trị này để quyết định có được phép bỏ job khỏi RAM hay không: nếu đĩa
    ghi lỗi thì RAM là nơi duy nhất còn giữ kết quả.
    """
    path = _status_path(job_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Không ghi result khổng lồ quá thường xuyên — luôn ghi khi done/error.
        # Ghi qua file .tmp rồi rename: nguyên tử, tránh status.json bị cắt dở
        # nếu process chết giữa chừng (reader cũng không đọc được file ghi dở).
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as e:
        log.warning("Không ghi được status job %s: %s", job_id, e)
        return False


def _load_job_from_disk(job_id: str) -> dict | None:
    try:
        data = json.loads(_status_path(job_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


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
    if not _LANGUAGE_RE.fullmatch(language.lower()):
        raise HTTPException(400, "Ngôn ngữ không hợp lệ")
    if len(glossary) > _MAX_GLOSSARY_CHARS:
        raise HTTPException(400, "Glossary quá dài (tối đa 100 KB)")
    num_speakers = max(0, min(_MAX_SPEAKERS, num_speakers))
    name = Path(file.filename or "input")
    if not media.is_supported(name):
        raise HTTPException(400, f"Định dạng {name.suffix} chưa hỗ trợ")
    # Client khai báo sẵn kích thước (Content-Length part) thì từ chối sớm,
    # khỏi ghi hàng GB rồi mới báo lỗi. Trường hợp không khai báo vẫn bị chặn
    # bởi ngưỡng đếm byte trong vòng ghi bên dưới.
    declared = getattr(file, "size", None)
    if declared is not None and declared > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File lớn hơn {_MAX_UPLOAD_BYTES // (1 << 30)} GB — "
            "hãy nén hoặc cắt file rồi thử lại.",
        )

    job_id = uuid.uuid4().hex[:12]
    job = {
        "status": "running",
        "stage": "queued",
        "percent": 0,
        "message": "Đang chuẩn bị…",
        "filename": name.name[:_MAX_FILENAME_CHARS],
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
    input_path: Path | None = None
    try:
        job_dir = _job_dir(job_id)
        # _save_job ở trên đã tạo thư mục (ghi status.json) — exist_ok tránh FileExistsError 500
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / ("input" + name.suffix.lower())
        written = 0
        with input_path.open("wb") as f:
            while chunk := await file.read(1 << 20):
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        f"File lớn hơn {_MAX_UPLOAD_BYTES // (1 << 30)} GB — "
                        "hãy nén hoặc cắt file rồi thử lại.",
                    )
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
        # File input ghi dở (upload quá lớn, file quá dài, thread không start được)
        # không còn job nào dùng — xóa để không để lại hàng GB mồ côi trên đĩa.
        if input_path is not None:
            with suppress(OSError):
                input_path.unlink()
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


def _safe_stem(filename: str) -> str:
    """Tên file export từ filename do client gửi: lọc ký tự cấm trên Windows
    (\\ / : * ? " < > |) và ký tự điều khiển, giới hạn độ dài để không vượt
    giới hạn tên file của OS."""
    stem = _UNSAFE_STEM_CHARS.sub("_", Path(filename).stem)[:120].strip(" .")
    # Windows cấm đặt file trùng tên thiết bị kể cả khi kèm đuôi ("CON.docx")
    # và match trên phần trước dấu chấm đầu tiên ("con.heo.docx" vẫn là CON).
    if stem.split(".", 1)[0].upper() in _WIN_DEVICE_STEMS:
        stem = f"_{stem}"
    return stem or "transcript"


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, body: dict, request: Request):
    if int(request.headers.get("content-length") or 0) > _MAX_JSON_BODY:
        raise HTTPException(413, "Payload quá lớn")
    job = _get_job(job_id)
    if not (job.get("result") or {}).get("sentences"):
        raise HTTPException(409, "Job chưa xong")
    fmt = body.get("format", "docx")
    if fmt not in _EXPORTERS:
        raise HTTPException(400, "Định dạng không hợp lệ")
    names = _clean_names(body.get("names"))
    # Chỉ chuyển đúng các field của Sentence — status.json đọc từ đĩa có thể
    # chứa key lạ (hoặc entry không phải dict) khiến **-unpack nổ TypeError → 500.
    sentences = [
        Sentence(**{k: v for k, v in s.items() if k in _SENTENCE_FIELDS})
        for s in job["result"]["sentences"]
        if isinstance(s, dict)
    ]
    _apply_speaker_overrides(sentences, body.get("speakers"))
    stem = _safe_stem(job["filename"])
    out = _job_dir(job_id) / f"{stem}.{fmt}"
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
    p = Path(extracted).resolve() if isinstance(extracted, str) and extracted else None
    # Đường dẫn đọc từ status.json phải nằm trong thư mục job — nếu file đó bị
    # sửa/hỏng và trỏ ra ngoài thì từ chối, tránh đọc file bất kỳ trên đĩa.
    if p is None or not p.is_file() or not p.is_relative_to(_job_dir(job_id).resolve()):
        raise HTTPException(
            404, "Không có file audio tách riêng (đầu vào không phải video)"
        )
    return FileResponse(p, filename=_safe_stem(job["filename"]) + p.suffix)


def _free_port(start: int = 8756) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Không tìm được port trống")


def main() -> None:
    from . import janitor  # chỉ cần lúc khởi động — import cục bộ

    port = _free_port()
    # GC thư mục jobs/ một lần trước khi nhận request: xóa job quá 30 ngày,
    # cap tổng 20 GB (xóa cũ nhất trước, giữ 10 job mới nhất). Bọc try/except —
    # GC lỗi không được chặn server chạy.
    try:
        gc = janitor.cleanup_jobs_dir(config.jobs_dir())
        log.info(
            "GC jobs/: xóa %d job, giữ %d, giải phóng %.1f MB",
            gc["removed"],
            gc["kept"],
            gc["freed_bytes"] / (1 << 20),
        )
    except Exception as e:
        log.warning("GC jobs/ lỗi (bỏ qua, server vẫn chạy): %s", e)
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"\n  ViTranscript đang chạy tại http://127.0.0.1:{port}  (Ctrl+C để thoát)\n")
    # log_level info để thấy job start/end khi debug
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
