# Hướng dẫn cho AI: cài ViTranscript giúp người dùng

> **File này viết cho trợ lý AI** (Claude, Claude Code, ChatGPT, Codex, Gemini, Cursor…)
> đang được người dùng nhờ *“cài ViTranscript cho tôi”*.
> Người dùng thường **không phải dân kỹ thuật**. Mục tiêu: app mở được trong trình duyệt,
> người dùng tự chọn file ghi âm và lấy transcript.
>
> Bỏ qua `CLAUDE.md` / `AGENTS.md` khi làm việc này — hai file đó dành cho developer
> (quy tắc commit, cập nhật trạng thái task…). **Không commit, không sửa code** khi chỉ cài đặt.

---

## 0. Nguyên tắc khi làm việc với người dùng

1. **Nói tiếng Việt, câu ngắn, không thuật ngữ.** Gọi Terminal / PowerShell là “cửa sổ gõ lệnh”.
2. **Xác định bạn có chạy được lệnh trên máy họ không:**
   - **Có** (Claude Code, Codex CLI, Cursor, Claude Desktop có quyền terminal…): tự chạy các lệnh dưới đây,
     báo ngắn gọn từng bước đang làm.
   - **Không** (ChatGPT/Claude trên web, app điện thoại): đưa **từng lệnh một**, bảo họ dán vào cửa sổ gõ lệnh,
     nhấn Enter, rồi **dán lại kết quả** cho bạn. Không đưa cả loạt lệnh một lúc.
3. **Hỏi trước khi** cài phần mềm hệ thống (Git, Xcode tools), đổi PATH, hoặc xóa thư mục.
4. **Không bao giờ** dùng `sudo`, không tắt Gatekeeper / SmartScreen / antivirus toàn hệ thống,
   không chạy script lạ ngoài danh sách trong file này.
5. App chạy **hoàn toàn trên máy** — không cần tài khoản, API key hay token. Nếu thấy mình sắp
   hỏi người dùng một key nào đó → bạn đang đi sai hướng.

---

## 1. Kiểm tra máy

| Yêu cầu | Mức tối thiểu |
|---|---|
| Hệ điều hành | macOS 12+ (Apple Silicon hoặc Intel), Windows 10/11 64-bit. Linux chạy được nhưng không phải mục tiêu chính |
| RAM | 8 GB (16 GB nếu muốn dùng model `phowhisper-large`) |
| Ổ trống | ~3 GB cho model mặc định; ~6 GB nếu dùng model lớn |
| Mạng | Cần khi cài và lần đầu tải model; sau đó chạy offline |

Lệnh xác định hệ điều hành nếu chưa rõ:
- macOS / Linux: `uname -sm`
- Windows (PowerShell): `[Environment]::OSVersion; $env:PROCESSOR_ARCHITECTURE`

**Không cần** cài Python, ffmpeg, CUDA hay GPU — `uv` tự tải Python 3.12, ffmpeg có sẵn qua dependency.

---

## 2. Tải mã nguồn về máy

Chọn thư mục dễ tìm, ví dụ thư mục chính của người dùng (`~` trên Mac, `%USERPROFILE%` trên Windows).

**Cách A — có Git** (kiểm tra: `git --version`):

```bash
cd ~
git clone https://github.com/coachingbusinessvn/cba_Transcript_local.git ViTranscript
cd ViTranscript
```

Windows (PowerShell):

```powershell
cd $env:USERPROFILE
git clone https://github.com/coachingbusinessvn/cba_Transcript_local.git ViTranscript
cd ViTranscript
```

Nếu chưa có Git:
- macOS: chạy `git --version` sẽ hiện hộp thoại cài *Command Line Tools* → bảo người dùng bấm **Install**, đợi xong rồi chạy lại.
- Windows: `winget install --id Git.Git -e` (hỏi người dùng trước), sau đó **mở cửa sổ PowerShell mới**.

**Cách B — không dùng Git** (dễ nhất cho người không rành máy):
bảo người dùng mở https://github.com/coachingbusinessvn/cba_Transcript_local → nút xanh **Code** →
**Download ZIP** → giải nén → đổi tên thư mục thành `ViTranscript` và để ở thư mục chính.

> Mọi lệnh từ đây trở đi chạy **bên trong thư mục `ViTranscript`**.

---

## 3. Cài đặt

### macOS / Linux

```bash
cd ~/ViTranscript
curl -LsSf https://astral.sh/uv/install.sh | sh     # bỏ qua nếu `uv --version` đã chạy được
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv sync
```

(Tương đương với nhấp đúp `install.command`. Nếu người dùng thích bấm chuột hơn: chuột phải
`install.command` → **Open** → **Open**.)

### Windows (PowerShell)

```powershell
cd $env:USERPROFILE\ViTranscript
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # bỏ qua nếu `uv --version` đã chạy được
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv python install 3.12
uv sync
```

(Tương đương với nhấp đúp `install.bat`. Nếu SmartScreen cảnh báo: **More info** → **Run anyway**.)

`uv sync` lần đầu mất khoảng 1–5 phút tùy mạng. Thành công khi không có dòng `error:` ở cuối.

---

## 4. Kiểm tra cài đặt thành công

```bash
uv run python -c "import app.server; print('OK')"
```

Phải in ra `OK`. Nếu lỗi → xem mục 7.

---

## 5. Chạy app

```bash
uv run python -m app.server
```

- Trình duyệt tự mở `http://127.0.0.1:8756` (hoặc cổng kế tiếp nếu 8756 bận — đọc dòng
  `ViTranscript đang chạy tại http://127.0.0.1:<port>` trong cửa sổ gõ lệnh).
- **Lệnh này chạy liên tục** cho tới khi đóng cửa sổ. Nếu bạn là agent tự chạy lệnh, hãy chạy nó
  ở chế độ nền / tiến trình riêng, đừng đợi nó kết thúc.
- Kiểm tra server sống (không bắt buộc): `curl -s http://127.0.0.1:8756/api/meta` trả về JSON.

Lần sau người dùng chỉ cần nhấp đúp **`run.command`** (Mac) hoặc **`run.bat`** (Windows) trong thư mục `ViTranscript`.
Nên đề nghị tạo lối tắt ra Desktop:
- macOS: `ln -s ~/ViTranscript/run.command ~/Desktop/ViTranscript.command`
- Windows: chuột phải `run.bat` → **Send to** → **Desktop (create shortcut)**.

---

## 6. Hướng dẫn người dùng lần đầu dùng

Giải thích ngắn gọn cho họ:

1. Bấm **Chọn file** → chọn file ghi âm/video (mp3, m4a, wav, mp4…).
2. Để model mặc định **phowhisper-small**. Lần đầu sẽ **tải model ~500 MB** — chậm là bình thường.
3. Bật **phân biệt người nói** nếu có nhiều người; số người = 0 để app tự đoán.
4. Bấm **Bắt đầu**, đợi thanh tiến trình. Thời gian xử lý thường xấp xỉ hoặc dài hơn độ dài file trên máy yếu.
5. Đổi tên người nói (Người 1 → tên thật), rồi tải **DOCX / Excel / SRT / TXT**.
6. Mỗi lần chỉ xử lý **một file**.

Muốn chính xác hơn và máy có ≥16 GB RAM: thử `phowhisper-medium` hoặc `phowhisper-large`.
Họp xen nhiều tiếng Anh: `large-v3-turbo`. Hướng dẫn chi tiết: `docs/HUONG-DAN-SU-DUNG.md`.

---

## 7. Xử lý lỗi thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `uv: command not found` / `'uv' is not recognized` | Mac: `export PATH="$HOME/.local/bin:$PATH"`. Windows: `$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"` hoặc mở cửa sổ PowerShell mới |
| Windows chặn chạy script (`running scripts is disabled`) | Dùng đúng lệnh có `-ExecutionPolicy ByPass` ở mục 3, **không** đổi policy toàn máy |
| macOS: *“không thể mở vì từ nhà phát triển không xác định”* | Chuột phải file → **Open** → **Open** |
| `uv sync` lỗi mạng / timeout | Kiểm tra mạng, tắt VPN/proxy công ty nếu có, chạy lại `uv sync` |
| `uv sync` lỗi về Python version | Chạy `uv python install 3.12` rồi `uv sync` lại. Không dùng Python hệ thống |
| Trình duyệt không tự mở | Mở thủ công địa chỉ in trong cửa sổ gõ lệnh |
| `Address already in use` / trang không vào được | Đóng cửa sổ ViTranscript cũ, chạy lại. App tự thử cổng 8756–8805 |
| Lỗi tải model (HuggingFace) | Kiểm tra mạng; thử lại. Không cần đăng nhập HuggingFace |
| Hết RAM / máy treo khi chạy | Đổi về `phowhisper-small`, tắt phân biệt người nói, hoặc cắt file ngắn hơn |
| Lỗi 409 trên giao diện | Đang có file khác xử lý — đợi xong |

Thư mục dữ liệu (model, cài đặt, job tạm) — xóa cả thư mục để reset app:
- macOS: `~/Library/Application Support/ViTranscript`
- Windows: `%APPDATA%\ViTranscript`
- Linux: `~/.local/share/ViTranscript`

Nếu vẫn lỗi: thu thập (1) hệ điều hành, (2) lệnh đã chạy, (3) ~30 dòng cuối của lỗi, và đề nghị
người dùng mở issue tại https://github.com/coachingbusinessvn/cba_Transcript_local/issues
(nhắc họ **không** đính kèm file ghi âm riêng tư).

---

## 8. Cập nhật bản mới

```bash
cd ~/ViTranscript        # Windows: cd $env:USERPROFILE\ViTranscript
git pull
uv sync
```

Nếu tải bằng ZIP: tải ZIP mới, giải nén đè lên thư mục cũ, rồi `uv sync`. Model và dữ liệu
người dùng nằm ở thư mục dữ liệu riêng nên không bị mất.

## 9. Gỡ cài đặt

Xóa thư mục `ViTranscript` và thư mục dữ liệu ở mục 7. (Tùy chọn: `uv` nằm ở `~/.local/bin/uv`.)
Hỏi người dùng xác nhận trước khi xóa.
