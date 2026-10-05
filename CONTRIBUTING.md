# Đóng góp cho ViTranscript

Cảm ơn bạn đã quan tâm! Mọi đóng góp đều được hoan nghênh: báo lỗi, sửa lỗi, cải thiện tài
liệu, đo WER trên dữ liệu thật, hay hỗ trợ thêm nền tảng.

*English speakers are welcome too: issues and PRs in English are fine.*

## Nguyên tắc của dự án

- **Local-first:** không gửi audio hay transcript ra dịch vụ bên ngoài, không thêm telemetry.
- **Chỉ dùng CPU, cài đặt nhẹ:** không kéo PyTorch/TensorFlow vào dependency.
- **Python 3.10–3.12** (`requires-python = ">=3.10,<3.13"`).
- **Giữ `onnxruntime<1.24`:** 1.23.x là bản cuối còn wheel cho macOS x86_64.
- **Nền tảng mục tiêu:** macOS arm64, macOS x86_64, Windows x64.
- **Model tải lúc chạy phải được ghim:** revision hoặc SHA-256 (xem `app/config.py`, `app/diarize.py`).
- **Text trên UI viết bằng tiếng Việt.** File `.bat` viết không dấu để tránh lỗi codepage.

## Thiết lập môi trường

Cần cài [`uv`](https://docs.astral.sh/uv/) trước.

```bash
uv sync                     # cài dependency (kèm nhóm dev: pytest, ruff, jiwer)
uv run python -m app.server # chạy app tại http://127.0.0.1:8756
```

## Trước khi mở PR

```bash
uv run ruff check .         # lint phải sạch
uv run pytest               # mọi test phải pass
```

- Viết test cho mọi thay đổi hành vi, đặt trong `tests/`. Test cần tải model thật thì gắn
  `@pytest.mark.model`; mặc định các test này không chạy.
- Giữ PR nhỏ, mỗi PR một mục đích. Mô tả rõ *vì sao* thay đổi, kèm cách bạn đã kiểm tra.
- Nếu đổi endpoint, middleware hay cách xử lý file, đọc qua [`SECURITY.md`](SECURITY.md)
  để không làm yếu các lớp bảo vệ hiện có.
- Nếu thêm model hoặc thư viện mới, cập nhật [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Báo lỗi

Mở issue theo mẫu **Bug report** và ghi rõ: hệ điều hành, model đã dùng, độ dài file, và log
trong cửa sổ terminal. **Đừng đính kèm ghi âm hay transcript có thông tin cá nhân.** Nếu
cần mẫu để tái hiện, hãy tạo audio thử (ví dụ bằng lệnh `say` trên macOS).

## Tài liệu kỹ thuật

- [`docs/01-bai-toan.md`](docs/01-bai-toan.md): bài toán và các quyết định kỹ thuật đã chốt.
- [`docs/03-tasks.md`](docs/03-tasks.md): trạng thái các task.
- `docs/dev/`: plan và spec chi tiết từ quá trình phát triển.

Khi đóng góp, bạn đồng ý rằng phần đóng góp được phát hành theo [MIT License](LICENSE) và
tuân theo [Quy tắc ứng xử](CODE_OF_CONDUCT.md).
