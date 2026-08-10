#!/usr/bin/env python3
"""Headless e2e: onefile sidecar READY → local job tiny-test → export TXT → shutdown.

Usage:
  python scripts/e2e_sidecar_linux.py --sidecar path/to/vitranscript-sidecar
  python scripts/e2e_sidecar_linux.py --sidecar ... --data-home /shared/cache
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

READY_RE = re.compile(r"^VITRANSCRIPT_READY http://127\.0\.0\.1:(\d+)$")
TOKEN = "e2e-sidecar-token-" + "a" * 32


def http_json(
    method: str,
    url: str,
    headers: dict | None = None,
    body: dict | None = None,
    timeout: float = 30,
):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        status = resp.status
    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return status, raw.decode("utf-8", errors="replace")


def _stdout_reader(proc: subprocess.Popen, line_q: queue.Queue[str | None]) -> None:
    """Background reader — avoids blocking forever on readline (R2-8)."""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line_q.put(line)
    except Exception as e:  # noqa: BLE001
        line_q.put(f"[reader-error] {e}\n")
    finally:
        line_q.put(None)


def wait_ready(
    proc: subprocess.Popen,
    line_q: queue.Queue[str | None],
    deadline: float,
    log_tail: list[str],
) -> int | None:
    """Read READY with monotonic deadline; never block past deadline."""
    port = None
    while time.monotonic() < deadline:
        if proc.poll() is not None and line_q.empty():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            line = line_q.get(timeout=min(0.2, remaining))
        except queue.Empty:
            continue
        if line is None:
            break
        line = line.rstrip("\n")
        log_tail.append(line)
        if len(log_tail) > 200:
            del log_tail[:-200]
        print(f"[sidecar] {line}")
        m = READY_RE.match(line)
        if m:
            port = int(m.group(1))
            break
    return port


def kill_reap(proc: subprocess.Popen, log_tail: list[str], reason: str) -> None:
    print(f"ERROR: {reason}", file=sys.stderr)
    if log_tail:
        print("--- sidecar log tail ---", file=sys.stderr)
        for ln in log_tail[-40:]:
            print(ln, file=sys.stderr)
        print("--- end tail ---", file=sys.stderr)
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar", required=True, type=Path)
    ap.add_argument("--wav", type=Path, default=None, help="Optional prebuilt WAV")
    ap.add_argument("--timeout", type=int, default=600, help="Job poll timeout seconds")
    ap.add_argument(
        "--data-home",
        type=Path,
        default=None,
        help="Shared XDG_DATA_HOME (model cache). Reuse across online/offline runs.",
    )
    ap.add_argument(
        "--ready-timeout",
        type=int,
        default=90,
        help="Seconds to wait for READY line",
    )
    args = ap.parse_args()

    sidecar: Path = args.sidecar.resolve()
    if not sidecar.is_file():
        print(f"ERROR: sidecar not found: {sidecar}", file=sys.stderr)
        return 1
    os.chmod(sidecar, os.stat(sidecar).st_mode | 0o111)

    # Generate test audio if needed
    wav = args.wav
    if wav is None:
        wav = Path(tempfile.gettempdir()) / "vitranscript-e2e-sample.wav"
        script = Path(__file__).resolve().parent / "gen_test_audio_linux.sh"
        subprocess.check_call(["bash", str(script), str(wav)])
    if not wav.is_file():
        print(f"ERROR: wav missing: {wav}", file=sys.stderr)
        return 1

    if args.data_home is not None:
        data_home = args.data_home.resolve()
        data_home.mkdir(parents=True, exist_ok=True)
    else:
        data_home = Path(tempfile.mkdtemp(prefix="vitranscript-e2e-data-"))
    print(f"==> XDG_DATA_HOME={data_home}")

    env = os.environ.copy()
    env["VITRANSCRIPT_INSTANCE_TOKEN"] = TOKEN
    env["VITRANSCRIPT_ENABLE_TEST_MODEL"] = "1"
    env["VITRANSCRIPT_DESKTOP"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["XDG_DATA_HOME"] = str(data_home)

    print(f"==> start sidecar {sidecar}")
    proc = subprocess.Popen(
        [str(sidecar), "--port", "0", "--no-browser"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    line_q: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(target=_stdout_reader, args=(proc, line_q), daemon=True)
    reader.start()
    log_tail: list[str] = []

    try:
        deadline = time.monotonic() + args.ready_timeout
        port = wait_ready(proc, line_q, deadline, log_tail)
        if port is None:
            kill_reap(proc, log_tail, "no READY line before deadline")
            return 1

        status, health = http_json("GET", f"http://127.0.0.1:{port}/healthz", timeout=2)
        print("healthz", status, health)
        if status != 200 or not isinstance(health, dict) or health.get("port") != port:
            kill_reap(proc, log_tail, "health mismatch")
            return 1

        # Self-test already covered natives; run one local job tiny-test diarize=false
        body = {
            "path": str(wav.resolve()),
            "model": "tiny-test",
            "language": "vi",
            "diarize": False,
            "punctuate": False,
            "num_speakers": 0,
            "glossary": "",
        }
        st, job = http_json(
            "POST",
            f"http://127.0.0.1:{port}/api/jobs/local",
            headers={"X-ViTranscript-Token": TOKEN},
            body=body,
            timeout=30,
        )
        print("create job", st, job)
        if st != 200 or not isinstance(job, dict) or "job_id" not in job:
            kill_reap(proc, log_tail, "create local job failed")
            return 1
        job_id = job["job_id"]

        t0 = time.monotonic()
        while time.monotonic() - t0 < args.timeout:
            st, j = http_json("GET", f"http://127.0.0.1:{port}/api/jobs/{job_id}", timeout=10)
            if not isinstance(j, dict):
                print("bad status", j)
                time.sleep(2)
                continue
            print(f"  status={j.get('status')} percent={j.get('percent')} msg={j.get('message')}")
            if j.get("status") == "error":
                kill_reap(proc, log_tail, f"job error: {j.get('message')}")
                return 1
            if j.get("status") == "done":
                break
            time.sleep(2)
        else:
            kill_reap(proc, log_tail, "job timeout")
            return 1

        # Export TXT
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/jobs/{job_id}/export",
            data=json.dumps({"format": "txt", "names": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
            code = resp.status
        print(f"export status={code} bytes={len(content)}")
        if code != 200 or len(content) == 0:
            kill_reap(proc, log_tail, "empty export")
            return 1
        text = content.decode("utf-8", errors="replace")
        if not text.strip():
            kill_reap(proc, log_tail, "export text empty")
            return 1
        print("export sample:", text[:200].replace("\n", " | "))

        # Shutdown
        st, _ = http_json(
            "POST",
            f"http://127.0.0.1:{port}/api/shutdown",
            headers={"X-ViTranscript-Token": TOKEN},
            timeout=5,
        )
        print("shutdown", st)
        if st != 202:
            kill_reap(proc, log_tail, "shutdown not 202")
            return 1
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill_reap(proc, log_tail, "process did not exit in 5s")
            return 1
        print("exit code", proc.returncode)
        print("E2E_SIDECAR PASS")
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass


if __name__ == "__main__":
    sys.exit(main())
