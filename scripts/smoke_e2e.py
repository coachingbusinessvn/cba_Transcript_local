"""Smoke test end-to-end trên máy dev (macOS): sinh audio 2 giọng bằng `say`,
chạy pipeline với model tiny, in kết quả. Chạy: uv run python scripts/smoke_e2e.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import config, export, pipeline
from app.segment import Sentence

# đăng ký model tiny (75MB) chỉ cho smoke test
config.MODEL_REGISTRY["tiny-test"] = {"source": "tiny", "label": "test", "size": "75MB"}

work = Path(tempfile.mkdtemp(prefix="vitranscript_smoke_"))
part_a, part_b = work / "a.aiff", work / "b.aiff"
subprocess.run(["say", "-v", "Linh", "-o", part_a,
                "Xin chào các bạn. Hôm nay chúng ta họp về dự án Vinamilk."], check=True)
subprocess.run(["say", "-v", "Samantha", "-o", part_b,
                "OK let me check the report."], check=True)
merged = work / "merged.m4a"
subprocess.run(["ffmpeg", "-y", "-i", part_a, "-i", part_b, "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1", merged], check=True, capture_output=True)

result = pipeline.run(
    merged, work / "job", "tiny-test", language="auto",
    enable_diarization=True, num_speakers=2,
    glossary_text="vina milk => Vinamilk\nVinamilk",
    progress=lambda st, p, m: print(f"  [{st} {p:.0f}%] {m}"),
)
sents = [Sentence(**s) for s in result["sentences"]]
for s in sents:
    print(f"{s.start:6.1f}–{s.end:6.1f}  SPK{s.speaker}  {s.text}")
export.to_docx(sents, work / "out.docx", "Smoke", None, None)
export.to_xlsx(sents, work / "out.xlsx", None)
assert (work / "out.docx").exists() and (work / "out.xlsx").exists()
print(f"\n✅ Smoke test OK — kết quả tại {work}")
