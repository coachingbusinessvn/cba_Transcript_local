# Đánh giá chất lượng transcript (WER)

Thư mục này dùng để đo **tỷ lệ lỗi từ (WER)** của pipeline trên audio hội thoại thật.

## Chuẩn bị file mẫu

Đặt **hai file** vào thư mục `eval/`:

| File | Nội dung |
|------|----------|
| `sample.*` | Audio/video hội thoại thật **3–5 phút** (vd. `sample.m4a`, `sample.wav`, `sample.mp3`, `sample.mp4`…) |
| `sample.txt` | Transcript gõ tay làm chuẩn: **đúng chính tả**, đủ nội dung nghe được. **Không bắt buộc** timestamp hay nhãn người nói. |

### Gợi ý khi gõ transcript chuẩn

- Ghi đúng những gì được nói (kể cả từ lóng, tên riêng).
- Không cần dấu thời gian (`00:01:23`) hay `SPK0`/`Người 1`.
- Mỗi dòng/câu cách nhau khoảng trắng là đủ — script sẽ chuẩn hóa trước khi so sánh.

### Riêng tư

File `eval/sample.*` là **dữ liệu cá nhân** — đã có trong `.gitignore` (`eval/sample.*`) và **không được commit** lên repo.

## Cách chạy

Từ thư mục gốc dự án:

```bash
uv run python scripts/eval_wer.py [model_key]
```

- Không truyền `model_key` → dùng model mặc định trong settings (thường `phowhisper-small`).
- Ví dụ so sánh model:

```bash
uv run python scripts/eval_wer.py phowhisper-small
uv run python scripts/eval_wer.py large-v3-turbo
```

Lần đầu chạy model sẽ tải về (cần mạng). Sau đó có thể chạy offline.

## Đọc kết quả WER

| WER | Ý nghĩa |
|-----|---------|
| **&lt; 15%** | Tốt |
| **15–30%** | Chấp nhận được |
| **&gt; 30%** | Xem lại model hoặc chất lượng ghi âm |

Ghi số liệu vào bảng WER trong [`docs/03-tasks.md`](../docs/03-tasks.md) khi so sánh model.

## Đánh giá phục hồi dấu câu

Tạo `punctuation_words.json` từ 3–5 phút ASR thô dưới dạng list object
`{"start": 0.0, "end": 0.5, "text": " xin"}`. Tạo
`punctuation_reference.txt` bằng đúng các lexical word đó, chỉ thêm viết hoa và dấu
`. , : ?`. Hai file là dữ liệu riêng tư, không commit.

Chạy `uv run python scripts/eval_punctuation.py`. Gate đạt khi boundary F1 tăng ít
nhất 10 điểm phần trăm và lexical WER so với ASR thô bằng 0.
