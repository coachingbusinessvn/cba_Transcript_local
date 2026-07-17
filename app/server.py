"""Web server local: FastAPI + job chạy nền trong thread. Chạy: python -m app.server"""
import socket
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import config, export, media, pipeline
from .segment import Sentence

app = FastAPI(title="ViTranscript")
JOBS: dict[str, dict] = {}
_STATIC = Path(__file__).parent / "static"
_EXPORTERS = {
    "docx": export.to_docx,
    "xlsx": export.to_xlsx,
    "srt": export.to_srt,
    "txt": export.to_txt,
}


def _any_job_running() -> bool:
    return any(j.get("status") == "running" for j in JOBS.values())


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


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
    }


def _run_job(job_id: str, input_path: Path, opts: dict) -> None:
    job = JOBS[job_id]

    def progress(stage: str, pct: float, msg: str):
        job.update(stage=stage, percent=round(pct, 1), message=msg)

    try:
        result = pipeline.run(
            input_path,
            input_path.parent,
            opts["model"],
            language=opts["language"],
            enable_diarization=opts["diarize"],
            num_speakers=opts["num_speakers"],
            glossary_text=opts["glossary"],
            progress=progress,
        )
        job.update(status="done", result=result, percent=100)
    except Exception as e:
        job.update(status="error", message=f"Lỗi: {e}", percent=100)


@app.post("/api/jobs")
async def create_job(
    file: Annotated[UploadFile, File()],
    model: Annotated[str, Form()],
    language: Annotated[str, Form()] = "vi",
    diarize: Annotated[bool, Form()] = True,
    num_speakers: Annotated[int, Form()] = 0,
    glossary: Annotated[str, Form()] = "",
):
    if _any_job_running():
        raise HTTPException(
            409,
            "Đang có job khác chạy. Vui lòng đợi xong rồi thử lại.",
        )
    if model not in config.MODEL_REGISTRY:
        raise HTTPException(400, "Model không hợp lệ")
    name = Path(file.filename or "input")
    if not media.is_supported(name):
        raise HTTPException(400, f"Định dạng {name.suffix} chưa hỗ trợ")

    job_id = uuid.uuid4().hex[:12]
    job_dir = config.jobs_dir() / job_id
    job_dir.mkdir(parents=True)
    input_path = job_dir / ("input" + name.suffix.lower())
    with input_path.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    config.save_settings({"model": model, "language": language})
    config.save_glossary_text(glossary)

    JOBS[job_id] = {
        "status": "running",
        "stage": "queued",
        "percent": 0,
        "message": "Đang chuẩn bị…",
        "filename": name.name,
    }
    opts = {
        "model": model,
        "language": language,
        "diarize": diarize,
        "num_speakers": num_speakers,
        "glossary": glossary,
    }
    threading.Thread(target=_run_job, args=(job_id, input_path, opts), daemon=True).start()
    return {"job_id": job_id}


def _get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "Không tìm thấy job")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return _get_job(job_id)


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, body: dict):
    job = _get_job(job_id)
    if job.get("status") != "done":
        raise HTTPException(409, "Job chưa xong")
    fmt = body.get("format", "docx")
    if fmt not in _EXPORTERS:
        raise HTTPException(400, "Định dạng không hợp lệ")
    names = body.get("names") or {}
    sentences = [Sentence(**s) for s in job["result"]["sentences"]]
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
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
