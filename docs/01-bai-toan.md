# Bài toán: Ứng dụng transcript hội thoại tiếng Việt — local-first

> Framing Brief theo phương pháp SID (frame). Ngày lập: 2026-07-17.

## 1. Topic

Ứng dụng local-first chạy trên macOS (Apple Silicon + Intel) và Windows (CPU-only), chuyển file ghi âm/ghi hình hội thoại thành văn bản có timestamp và người nói.

## 2. Problem + mục đích cuối

Người dùng có file mp3/m4a/mov/mp4 chứa hội thoại **~90% tiếng Việt, thi thoảng xen từ tiếng Anh**, cần:

1. Chọn file audio; nếu là video (mov/mp4) thì tự tách audio.
2. Transcript bằng model chạy local (không cloud, không phí API, bảo mật nội dung).
3. Xuất kết quả dạng subtitle có timestamp ra **DOCX** hoặc **XLSX** (kèm SRT/TXT).
4. Cho phép khai báo **từ khóa/glossary** để tool tự sửa thuật ngữ hay bị nhận sai.
5. **Tách câu tiếng Việt** và **phân biệt người nói** (speaker diarization).

## 3. Audience

Người dùng cuối **không rành công nghệ**: không biết Python, không tự cài thư viện. Yêu cầu trải nghiệm: double-click file cài đặt → double-click file chạy → chọn file → bấm nút → tải kết quả.

## 4. Scope

**In-scope (v1):**
- Input: mp3, m4a, wav, aac, flac, ogg + video mov, mp4, mkv, webm (tách audio bằng ffmpeg)
- Transcript: faster-whisper (CTranslate2, CPU int8), model đổi được trong UI
- Diarization: sherpa-onnx (pyannote segmentation 3.0 + 3D-Speaker embedding dạng ONNX)
- Glossary 2 tầng: hotwords khi decode + fuzzy find-replace sau decode
- Tách câu theo dấu câu Whisper + word-timestamps; đổi tên nhãn người nói trước khi xuất
- Export: DOCX (bảng), XLSX, SRT, TXT; tải lại file audio đã tách từ video
- UI: web local (localhost, mở bằng trình duyệt), tiếng Việt
- Cài đặt: script 1-click dùng `uv` (tự tải Python 3.12 + thư viện)

**Out-of-scope (v1), lý do:**
- Realtime/streaming — khác kiến trúc hoàn toàn, chưa cần
- Dịch thuật, tóm tắt — cần LLM, làm v2
- Sửa transcript trực tiếp trong app — tốn công UI lớn, tạm xuất file rồi sửa trong Word/Excel
- Xử lý hàng loạt nhiều file song song — máy CPU yếu sẽ nghẽn, v1 chạy tuần tự từng job
- Đóng gói .app/.exe ký số — làm v2 nếu cần phân phối rộng

## 5. Output & Task type

- **Output:** codebase chạy được + script cài đặt Mac/Windows + README tiếng Việt.
- **Task type:** software build (có nghiên cứu kỹ thuật đi kèm — đã chốt ở mục 7).

## 6. Rủi ro nếu framing sai

- Chọn stack cần PyTorch → bộ cài nặng thêm ~2GB, dễ lỗi trên máy người dùng → **đã né bằng CTranslate2 + ONNX**.
- Chọn model quá nặng làm mặc định → máy Windows CPU-only chạy quá chậm → mặc định PhoWhisper-small, cho đổi model.
- Kỳ vọng diarization hoàn hảo → thực tế ghi âm mic chung, giọng chồng lấn sẽ giảm độ chính xác đáng kể → cần nói rõ trong README.

## 7. Quyết định kỹ thuật đã chốt (với người dùng, 2026-07-17)

| Câu hỏi | Quyết định | Lý do |
|---|---|---|
| Máy mục tiêu | Mac M1–M4, Mac Intel, Windows CPU-only | Người dùng xác nhận, không có GPU NVIDIA |
| Engine transcript | faster-whisper (CTranslate2, int8) | Nhanh ~4x Whisper gốc, không cần PyTorch, wheel có đủ 3 nền tảng |
| Model mặc định | `diepho/PhoWhisper-small-ct2` | Ưu tiên tốc độ (người dùng chọn); PhoWhisper fine-tune 844h tiếng Việt |
| Model tùy chọn | PhoWhisper medium/large, large-v3-turbo, whisper-small | Đổi được trong settings; turbo tốt khi xen nhiều tiếng Anh |
| Diarization | sherpa-onnx (pyannote-segmentation-3.0 ONNX + eres2net embedding) | Không cần PyTorch, không cần HF token — 2 điểm đau lớn nhất của pyannote gốc |
| Sửa từ khóa | `hotwords` faster-whisper (tầng decode) + rapidfuzz find-replace (tầng hậu kỳ) | hotwords giới hạn ~224 token nên cần thêm tầng 2 không giới hạn |
| Tách câu | Dấu câu Whisper + word-timestamps, ngắt theo khoảng lặng >1.2s, trần 15s/40 từ | Whisper chấm câu tiếng Việt đủ tốt; không cần underthesea ở v1 |
| UI | Web UI local (FastAPI + 1 trang HTML) | Nhẹ nhất, chạy y hệt trên 3 nền tảng, không cần Electron |
| Cài đặt | Script 1-click dùng `uv` | `uv` tự tải Python — người dùng không cần biết Python là gì |
| ffmpeg | Dùng bản có sẵn trên máy, fallback `static-ffmpeg` qua pip | Người dùng không phải tự cài ffmpeg |

## 8. Tiêu chí nghiệm thu

1. Trên máy sạch (không có Python), double-click `install` → cài xong không lỗi.
2. Double-click `run` → trình duyệt tự mở UI tiếng Việt.
3. Nạp file mp4 30 phút → nhận được DOCX/XLSX có timestamp, người nói, câu tách hợp lý.
4. Khai báo glossary `nờ vi đi a => NVIDIA` + từ khóa `Vinamilk` → transcript ra đúng 2 từ này.
5. Toàn bộ chạy offline sau lần tải model đầu tiên (thử tắt mạng).
6. Chất lượng đo được bằng số: WER (tỷ lệ lỗi từ) ≤ 30% trên audio mẫu thật có transcript gõ tay làm chuẩn (golden file — Task 12b trong plan); mốc này dùng để so sánh khách quan khi đổi model/tham số.

**Confidence: Cao** cho stack và tính khả thi (đã verify model repos + URL tải hoạt động). **Trung bình** cho chất lượng diarization thực tế — phụ thuộc chất lượng ghi âm.
