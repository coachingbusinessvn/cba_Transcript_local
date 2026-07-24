"""Từ điển sửa lỗi (glossary): thiên vị model khi decode + tự sửa sau khi transcript.

Định dạng file glossary (mỗi dòng một mục, dòng bắt đầu # là ghi chú):
  từ sai => từ đúng      : luôn thay "từ sai" bằng "từ đúng" (không phân biệt hoa thường)
  Thuật Ngữ              : từ khóa cần giữ đúng — được đưa vào hotwords của model,
                           đồng thời các cụm gần giống trong transcript sẽ bị "hút" về đúng dạng này
"""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Chữ cái ASCII + toàn bộ dải chữ có dấu tiếng Việt
_LETTER = r"A-Za-zÀ-ỹ0-9"
_FUZZY_THRESHOLD = 88


@dataclass
class Glossary:
    replacements: list[tuple[str, str]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @property
    def hotwords(self) -> str:
        """Chuỗi đưa vào tham số hotwords của faster-whisper."""
        terms = [right for _, right in self.replacements] + self.keywords
        return ", ".join(dict.fromkeys(terms))  # bỏ trùng, giữ thứ tự


def parse(text: str) -> Glossary:
    g = Glossary()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            wrong, _, right = line.partition("=>")
            wrong, right = wrong.strip(), right.strip()
            if wrong and right:
                g.replacements.append((wrong, right))
        else:
            g.keywords.append(line)
    return g


def _boundary_pattern(term: str) -> re.Pattern:
    # \b không hoạt động tốt với chữ có dấu — dùng lookaround trên dải chữ tiếng Việt
    return re.compile(
        rf"(?<![{_LETTER}]){re.escape(term)}(?![{_LETTER}])", re.IGNORECASE
    )


def _fuzzy_snap(text: str, term: str) -> str:
    """Thay các cụm từ gần giống `term` (sai chính tả nhẹ) bằng đúng `term`."""
    n = len(term.split())
    words = text.split(" ")
    if len(words) < n:
        return text
    out, i = [], 0
    while i <= len(words) - n:
        chunk = " ".join(words[i : i + n])
        core = chunk.strip(".,!?;:…\"'()")
        if core and core.lower() != term.lower() and abs(len(core) - len(term)) <= 3:
            if fuzz.ratio(core.lower(), term.lower()) >= _FUZZY_THRESHOLD:
                out.append(chunk.replace(core, term))
                i += n
                continue
        out.append(words[i])
        i += 1
    out.extend(words[i:])
    return " ".join(out)


def correct(text: str, glossary: Glossary) -> str:
    for wrong, right in glossary.replacements:
        # Dùng hàm thay thế thay vì chuỗi mẫu: chuỗi glossary do người dùng nhập
        # có thể chứa "\" hoặc "\1" khiến re.sub hiểu là escape/backreference và lỗi.
        text = _boundary_pattern(wrong).sub(lambda _m, r=right: r, text)
    for term in glossary.keywords:
        if len(term) >= 4:  # từ quá ngắn dễ thay nhầm
            text = _fuzzy_snap(text, term)
    return text
