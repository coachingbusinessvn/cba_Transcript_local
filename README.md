# ViTranscript

**Phát triển bởi [Coaching Business](https://coachingbusiness.vn)** · mã nguồn mở, miễn phí, giấy phép MIT.

[![CI](https://github.com/coachingbusinessvn/cba_Transcript_local/actions/workflows/ci.yml/badge.svg)](https://github.com/coachingbusinessvn/cba_Transcript_local/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-blue)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)

> **English:** ViTranscript is a local-first desktop tool that turns Vietnamese audio and
> video into timestamped, speaker-labelled transcripts. It exports DOCX, XLSX, SRT and TXT.
> It runs fully offline on CPU (faster-whisper + PhoWhisper, sherpa-onnx diarization, ONNX
> punctuation restoration). Recordings never leave your machine. The UI and docs are in
> Vietnamese; contributions in English are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

Ứng dụng **local-first** chuyển hội thoại tiếng Việt (audio/video) thành văn bản có timestamp, phân biệt người nói, và xuất DOCX / Excel / SRT / TXT.

Mọi xử lý chạy **trên máy của bạn**. File ghi âm và transcript **không được tải lên server bên thứ ba**.

Lần đầu dùng model cần mạng để tải model về máy; sau đó có thể chạy offline.

> 📖 **Hướng dẫn đầy đủ (macOS & Windows), có khắc phục sự cố:** [`docs/HUONG-DAN-SU-DUNG.md`](docs/HUONG-DAN-SU-DUNG.md)

---

## Cài đặt nhanh: nhờ AI cài giúp

Không rành kỹ thuật? Mở Claude, ChatGPT, Gemini… (hoặc Claude Code / Codex nếu bạn có) và dán nguyên đoạn sau:

```text
Hãy cài giúp tôi ứng dụng ViTranscript (chuyển ghi âm tiếng Việt thành văn bản, chạy trên máy).
Mã nguồn: https://github.com/coachingbusinessvn/cba_Transcript_local
Làm đúng theo file hướng dẫn dành cho AI trong repo:
https://github.com/coachingbusinessvn/cba_Transcript_local/blob/main/CAI-DAT-BANG-AI.md
Máy của tôi là: [macOS / Windows]. Tôi không rành kỹ thuật — hãy hướng dẫn từng bước,
mỗi lần một lệnh, và chờ tôi gửi lại kết quả.
```

AI sẽ đọc [`CAI-DAT-BANG-AI.md`](CAI-DAT-BANG-AI.md) và dẫn bạn qua từng bước. Nếu AI không mở được đường link, hãy tải file đó về và đính kèm vào cuộc trò chuyện.

---

## Cài đặt thủ công

### macOS

1. Nhấp đúp file **`install.command`**.
2. Nếu macOS báo *“không thể mở vì từ nhà phát triển không xác định”*: **chuột phải** file → **Open** → chọn **Open** lần nữa.
3. Đợi cài xong (tự cài `uv` + Python 3.12 + thư viện). Khi thấy thông báo hoàn tất, đóng cửa sổ.

### Windows

1. Nhấp đúp file **`install.bat`**.
2. Nếu Windows SmartScreen cảnh báo: **More info** → **Run anyway**.
3. Đợi cài xong. Khi thấy thông báo hoàn tất, nhấn phím bất kỳ để đóng.

---

## Cách dùng

1. Nhấp đúp **`run.command`** (Mac) hoặc **`run.bat`** (Windows).
2. Trình duyệt sẽ tự mở giao diện ViTranscript (địa chỉ dạng `http://127.0.0.1:8756`).
3. **Chọn file** audio/video (mp3, m4a, wav, mp4, …).
4. Tuỳ chọn: model, ngôn ngữ, bật/tắt phân biệt người nói, số người nói (0 = tự đoán), glossary.
5. Bấm **Bắt đầu** và đợi thanh tiến trình hoàn tất.
6. **Đổi tên người nói** (nếu bật diarization) rồi **tải** DOCX / XLSX / SRT / TXT.
7. Sửa nhầm lẫn người nói: mỗi dòng transcript có dropdown chọn lại người nói trước khi xuất file (chỉnh sửa sống trong trang — refresh sẽ mất).

> **Lưu ý v1:** chỉ chạy **một job tại một thời điểm**. Nếu gửi job khi đang xử lý, hệ thống trả lỗi (HTTP 409) — đợi job hiện tại xong rồi thử lại.

---

## File dài (1–4 giờ)

- File **trên 2 giờ**: app tự tắt "phân biệt người nói" để tránh hết bộ nhớ — transcript và timestamp vẫn đầy đủ (có ghi chú vàng trên màn hình).
- File **trên 4 giờ**: app từ chối và khuyên cắt file thành phần ngắn hơn.
- Nếu app bị tắt giữa chừng (mất điện, đóng nhầm cửa sổ): mở lại app, phần transcript đã làm xong sẽ tự hiện lại — có thể xuất file ngay, hoặc chạy lại từ đầu để có bản đầy đủ.

---

## Phục hồi dấu câu

Tùy chọn **Tự chèn dấu câu** được bật mặc định và đặc biệt hữu ích với PhoWhisper.
Lần đầu dùng, app tải thêm model ViBERT-CAPU ONNX INT8 khoảng 110 MB; các lần sau
chạy offline. Bước này chỉ đổi viết hoa và thêm `. , : ?`, không đổi chính tả hoặc
timestamp.

Nếu model dấu câu không tải/chạy được, job vẫn hoàn tất bằng transcript gốc và hiện
cảnh báo vàng. Có thể tắt tùy chọn để dùng đúng cách tách câu cũ.

Nguồn và license model: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

## Từ điển sửa lỗi (Glossary)

Trong ô glossary (mỗi dòng một mục; dòng bắt đầu bằng `#` là ghi chú):

| Cú pháp | Ý nghĩa |
|---------|---------|
| `sai => đúng` | Luôn thay cụm “sai” bằng “đúng” (không phân biệt hoa/thường) |
| `Thuật Ngữ` | Từ khóa cần giữ đúng: gợi ý cho model + “hút” các dạng gần giống về đúng chính tả |

**Ví dụ:**

```text
# Sửa lỗi hay gặp
vina milk => Vinamilk
nờ vi đi a => NVIDIA
cô vít => COVID

# Từ khóa / tên riêng
Vinamilk
NVIDIA
COVID-19
Phòng Kinh doanh
```

Glossary được lưu trên máy và dùng lại lần sau.

---

## Chọn model nào?

| Model (key) | Tốc độ | Độ chính xác (TV) | Dung lượng | WER (audio mẫu) | Gợi ý |
|-------------|--------|-------------------|------------|-----------------|-------|
| **phowhisper-small** (mặc định) | Nhanh | Tốt cho tiếng Việt | ~490 MB | chưa đo — cần `eval/sample` | Máy yếu / muốn nhanh |
| **phowhisper-medium** | Trung bình (~2× chậm hơn small) | Chính xác hơn small | ~1.5 GB | chưa đo — cần `eval/sample` | Cân bằng |
| **phowhisper-large** | Chậm | Chính xác nhất cho tiếng Việt | ~3 GB | chưa đo — cần `eval/sample` | Máy mạnh, ưu tiên chất lượng |
| **large-v3-turbo** | Khá nhanh (large) | Tốt khi xen nhiều tiếng Anh | ~1.6 GB | chưa đo — cần `eval/sample` | Họp song ngữ VI–EN |
| **whisper-small** | Nhanh | Đa ngôn ngữ, TV kém PhoWhisper | ~490 MB | chưa đo — cần `eval/sample` | Nội dung đa ngôn ngữ nhẹ |

Đo WER khách quan: xem [`eval/README.md`](eval/README.md) và chạy `uv run python scripts/eval_wer.py [model_key]`.

**Mốc WER:** &lt;15% tốt · 15–30% chấp nhận được · &gt;30% xem lại model/chất lượng ghi âm.

---

## Giới hạn cần biết

- **Phân biệt người nói** phụ thuộc chất lượng ghi âm: mic chung, giọng chồng lấn, ồn nền sẽ giảm độ chính xác.
- **Lần đầu** dùng mỗi model cần **mạng** để tải về (vài trăm MB đến ~3 GB). Lần sau **offline** được.
- Model **lớn** tốn **RAM** và thời gian hơn; máy chỉ vài GB RAM nên dùng `phowhisper-small` hoặc `whisper-small`.
- v1 **không** chạy song song nhiều file; app tự dọn job cũ mỗi lần khởi động (xem mục Thư mục dữ liệu).

---

## Troubleshooting

### Thư mục dữ liệu trên máy

App lưu model đã tải, settings, glossary và job tạm tại:

| Hệ điều hành | Đường dẫn |
|--------------|-----------|
| **macOS** | `~/Library/Application Support/ViTranscript` |
| **Windows** | `%APPDATA%\ViTranscript` (thường `C:\Users\<tên>\AppData\Roaming\ViTranscript`) |
| **Linux** | `~/.local/share/ViTranscript` (hoặc `$XDG_DATA_HOME/ViTranscript`) |

Xóa **cả thư mục** trên = reset app (sẽ tải lại model lần sau).

**Tự động dọn job cũ:** mỗi lần khởi động, app tự xóa các job trong `jobs/` có kết quả cũ hơn **30 ngày**; nếu tổng `jobs/` vượt **20 GB** thì xóa tiếp job cũ nhất trước nhưng luôn giữ lại **10 job gần nhất**. Job đang chạy mới được giữ lại; job `running` cũ hơn 30 ngày (thường là do app bị tắt/crash giữa chừng) vẫn bị xóa theo tuổi, còn luật giới hạn 20 GB không bao giờ xóa job đang chạy. Không cần dọn tay — nhưng vẫn có thể xóa thủ công `jobs/` nếu muốn giải phóng chỗ ngay.

### Cổng (port) bị bận

Server tự tìm cổng trống bắt đầu từ **8756** (8756–8805). Nếu địa chỉ tự mở không vào được: đọc dòng `ViTranscript đang chạy tại http://127.0.0.1:<port>` trong cửa sổ terminal/CMD và mở đúng địa chỉ đó. Muốn giải phóng cổng cũ: đóng cửa sổ terminal/app ViTranscript cũ rồi chạy lại `run.command` / `run.bat`.

### macOS Gatekeeper chặn `install.command` / `run.command`

**Chuột phải** file → **Open** → xác nhận **Open**. Không cần tắt Gatekeeper toàn hệ thống.

### ffmpeg

App ưu tiên `ffmpeg` có sẵn trên PATH; nếu thiếu sẽ **tự dùng static-ffmpeg** (kèm theo dependency). Không cần cài ffmpeg thủ công trong hầu hết trường hợp.

> Bản static-ffmpeg được tải từ GitHub và **không kiểm tra checksum**. Nếu cần mức tin cậy cao,
> hãy cài ffmpeg từ nguồn chính thức (Homebrew, winget…) trước khi chạy app. Xem
> [`SECURITY.md`](SECURITY.md).

### Windows: không tìm thấy `uv` sau khi cài

1. **Đóng và mở lại** cửa sổ CMD/PowerShell (hoặc đăng xuất/đăng nhập).
2. Hoặc thêm `%USERPROFILE%\.local\bin` vào **PATH** hệ thống, rồi mở terminal mới.
3. Kiểm tra: `uv --version`.

### Windows: `run.bat` nháy cửa sổ rồi tắt ngay

Mở `cmd.exe`, `cd` tới thư mục app rồi chạy tay `uv run python -m app.server` để đọc lỗi
(`run.bat` không có `pause` nên cửa sổ tự đóng khi lỗi).

> **Checklist verify đầy đủ trên Windows thật** (cài đặt → chạy → upload/export → edge cases):
> [`docs/13-windows-verification-checklist.md`](docs/13-windows-verification-checklist.md)

### Job bị kẹt / lỗi giữa chừng

- Xem thông báo trên UI.
- Thử model nhỏ hơn hoặc file ngắn hơn.
- App đã tự dọn `jobs/` mỗi lần khởi động (>30 ngày hoặc >20 GB, giữ 10 job mới nhất); nếu vẫn cần thêm chỗ, xóa tay thư mục `jobs` trong thư mục data (bảng trên).

---

## Ghi chú cho developer

```bash
export PATH="$HOME/.local/bin:$PATH"
uv sync                          # cài dependency (+ dev: pytest, ruff, jiwer)
uv run python -m app.server      # chạy server local
uv run pytest                    # unit tests
uv run ruff check .              # lint
uv run python scripts/smoke_e2e.py   # smoke E2E (macOS, cần `say` + ffmpeg)
uv run python scripts/eval_wer.py [model_key]  # WER trên eval/sample.*
uv run python scripts/smoke_punctuation_model.py  # smoke model pin, lần đầu cần mạng
uv run python scripts/eval_punctuation.py         # boundary F1, cần fixture riêng tư
```

Tài liệu kỹ thuật: [`docs/01-bai-toan.md`](docs/01-bai-toan.md), [`docs/02-plan.md`](docs/02-plan.md), [`docs/03-tasks.md`](docs/03-tasks.md).

---

## Đóng góp & bảo mật

- Hướng dẫn đóng góp: [`CONTRIBUTING.md`](CONTRIBUTING.md) · Quy tắc ứng xử: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- Báo lỗ hổng bảo mật (kênh riêng tư): [`SECURITY.md`](SECURITY.md)

## License

Mã nguồn ViTranscript phát hành theo [MIT License](LICENSE).
App không đóng gói model hay ffmpeg, mà tải chúng về lúc chạy. Mỗi thành phần đó giữ license
riêng (PhoWhisper: BSD-3-Clause, ViBERT-CAPU: CC-BY-SA-4.0, FFmpeg: LGPL/GPL…). Xem
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

<p align="center">ViTranscript được phát triển và duy trì bởi <a href="https://coachingbusiness.vn"><strong>Coaching Business</strong></a>.</p>
