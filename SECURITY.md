# Chính sách bảo mật / Security policy

## Báo cáo lỗ hổng

**Đừng mở issue công khai cho lỗ hổng bảo mật.** Hãy báo riêng qua
[GitHub Security Advisories](https://github.com/coachingbusinessvn/cba_Transcript_local/security/advisories/new): tab **Security** → **Report a vulnerability**.

Báo cáo nên có:

- phiên bản hoặc commit, và hệ điều hành;
- các bước tái hiện, hoặc một PoC tối thiểu;
- tác động bạn đánh giá được (đọc/ghi file, chạy lệnh, lộ transcript…).

Chúng tôi sẽ cố gắng phản hồi trong vòng 7 ngày. Bản vá sẽ phát hành cùng một advisory
ghi công người báo, trừ khi bạn không muốn được nêu tên.

*English:* please report vulnerabilities privately via GitHub Security Advisories (link above),
not via public issues.

## Phạm vi và mô hình mối đe dọa

ViTranscript là ứng dụng **chạy trên một máy, cho một người dùng**. Server FastAPI chỉ bind
`127.0.0.1`, và các lớp bảo vệ hiện có là:

- **Chống DNS rebinding:** header `Host` phải là địa chỉ loopback.
- **Chống CSRF:** request ghi phải có `Origin` trùng đúng origin của server, và
  `Sec-Fetch-Site: cross-site` bị chặn.
- **Chống path traversal:** `job_id` chỉ nhận dạng hex-12; file audio phải nằm trong thư mục
  của job.
- **Giới hạn kích thước request:** upload tối đa 8 GB, kiểm tra `Content-Length` trước khi
  parse multipart; body JSON tối đa 4 MB.
- **Security header:** CSP, `X-Frame-Options: DENY`, `nosniff`, `no-store` cho `/api/`.

Những trường hợp sau **nằm ngoài phạm vi**:

- **Phần mềm độc hại khác chạy trên cùng máy** với quyền của người dùng. Nó có thể đọc thẳng
  thư mục dữ liệu của app.
- **Tự ý mở server ra mạng**, ví dụ sửa code để bind `0.0.0.0` hoặc dùng reverse proxy.

## Chuỗi cung ứng: những gì được tải lúc chạy

| Thành phần | Nguồn | Kiểm tra toàn vẹn |
|---|---|---|
| Model Whisper | Hugging Face (repo trong `app/config.py`) | Ghim commit (`revision`) |
| Model dấu câu ViBERT-CAPU | Hugging Face | Ghim commit + SHA-256 |
| Model diarization | GitHub Releases của sherpa-onnx | SHA-256 |
| FFmpeg (dự phòng) | gói `static-ffmpeg` → GitHub `zackees/ffmpeg_bins` | **Không có checksum** |
| `uv` (trong script cài đặt) | `astral.sh` qua HTTPS | Theo script chính thức của Astral |

**Lưu ý về FFmpeg:** app ưu tiên `ffmpeg`/`ffprobe` có sẵn trên `PATH`. Chỉ khi không tìm
thấy, gói `static-ffmpeg` mới tải một bản build dựng sẵn mà không kiểm tra checksum. Nếu bạn
cần mức tin cậy cao hơn, hãy cài FFmpeg từ nguồn chính thức hoặc từ trình quản lý gói của hệ
điều hành (Homebrew, winget, apt) trước khi chạy app.
