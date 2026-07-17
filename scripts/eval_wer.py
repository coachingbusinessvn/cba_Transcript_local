"""Đo tỷ lệ lỗi từ (WER) của pipeline trên audio mẫu thật.

Chuẩn bị theo eval/README.md. Chạy: uv run python scripts/eval_wer.py [model_key]
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from jiwer import wer

from app import config, pipeline

EVAL = Path(__file__).parent.parent / "eval"


def normalize(t: str) -> str:
    t = re.sub(r"[^\wÀ-ỹ ]", " ", t.lower())
    return " ".join(t.split())


ref_path = EVAL / "sample.txt"
audio = next((p for p in EVAL.glob("sample.*") if p.suffix != ".txt"), None)
if not audio or not ref_path.exists():
    sys.exit("Thiếu eval/sample.<audio> hoặc eval/sample.txt — xem eval/README.md")

model_key = sys.argv[1] if len(sys.argv) > 1 else config.load_settings()["model"]
work = Path(tempfile.mkdtemp(prefix="vitranscript_eval_"))
result = pipeline.run(audio, work, model_key, enable_diarization=False,
                      progress=lambda st, p, m: print(f"  [{st} {p:.0f}%] {m}"))
hyp = " ".join(s["text"] for s in result["sentences"])
score = wer(normalize(ref_path.read_text(encoding="utf-8")), normalize(hyp))
print(f"\nModel: {model_key}\nWER: {score:.1%}")
print("Mốc tham khảo: <15% tốt · 15–30% chấp nhận được · >30% xem lại model/chất lượng ghi âm")
