# ViTranscript — thiết kế phục hồi dấu câu tiếng Việt

**Ngày:** 2026-07-19

**Trạng thái:** Người dùng đã duyệt ngày 2026-07-19; sẵn sàng triển khai theo plan

**Phạm vi:** Phục hồi dấu câu và viết hoa sau ASR, trước khi tách câu

**Nhánh hiện tại:** `feature/long-audio-robustness`

## 1. Kết quả cần đạt

PhoWhisper thường trả văn bản ít dấu câu. `build_sentences()` vì thế phải dựa nhiều
vào khoảng lặng và trần 20 giây/55 từ, dẫn tới các câu bị cắt giữa mệnh đề.

Feature này thêm một bước phục hồi dấu câu tiếng Việt ngay sau transcript. Đầu ra
phải có thêm `.`, `,`, `:` và `?` cùng viết hoa phù hợp, để logic tách câu hiện có
nhìn thấy biên ngôn ngữ tự nhiên hơn.

Yêu cầu quan trọng hơn chất lượng trình bày là bảo toàn dữ liệu gốc:

- số lượng `Word` không đổi;
- `start` và `end` của từng `Word` không đổi tuyệt đối;
- không thêm, xóa, nối, thay thế hoặc sửa chính tả từ;
- chỉ được đổi hoa/thường và gắn dấu câu;
- nếu model không dùng được, job vẫn hoàn tất bằng transcript gốc và báo rõ cảnh báo.

## 2. Bối cảnh và quyết định đã chốt

### 2.1 Vị trí trong pipeline

Chọn phục hồi ở mức từ, trước `build_sentences()`:

```text
convert → transcribe → restore punctuation → diarize → build sentences
        → glossary correction → assign speakers → export
```

Không chọn phục hồi sau `build_sentences()`, vì khi đó dấu câu chỉ làm văn bản đẹp
hơn nhưng không sửa được biên câu đã bị cắt.

### 2.2 Backend model

Cuộc trao đổi ban đầu chọn model `dragonSwing/vibert-capu` chạy PyTorch. Khi viết
spec, dự án đã có lại ràng buộc cứng “không dependency kéo theo PyTorch/TensorFlow”
và đã xuất hiện bản ONNX phù hợp. Thiết kế hành vi PA1 không đổi, nhưng backend được
chuyển sang:

| Thuộc tính | Giá trị khóa trong spec |
|---|---|
| Repository | `welcomyou/vibert-capu-onnx` |
| Revision | `a7754d037f4a9e29f7f3224f27acb60149eab874` |
| Artifact | `vibert-capu.int8.onnx` |
| Kích thước | `115,707,731` byte (~110 MiB) |
| SHA-256/LFS OID | `67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa` |
| Runtime | ONNX Runtime, `CPUExecutionProvider` |
| License model | CC-BY-SA-4.0 |

Model gốc công bố hỗ trợ viết hoa và bốn dấu `. , : ?`; bản INT8 công bố là bản
quantize động của cùng model. ViTranscript không tự động nâng revision: đổi model
hoặc hash là một thay đổi được review và benchmark riêng.

Nguồn tham chiếu:

- [Model gốc `dragonSwing/vibert-capu`](https://huggingface.co/dragonSwing/vibert-capu)
- [Artifact ONNX INT8](https://huggingface.co/welcomyou/vibert-capu-onnx)
- [Revision đã pin](https://huggingface.co/welcomyou/vibert-capu-onnx/tree/a7754d037f4a9e29f7f3224f27acb60149eab874)

### 2.3 Lý do chọn ONNX INT8

- giữ đúng kiến trúc local-first, CPU-only của dự án;
- không thêm PyTorch hoặc TensorFlow;
- model khoảng 110 MiB thay vì weight PyTorch khoảng 462 MB cộng runtime lớn;
- cùng họ runtime ONNX đang dùng cho diarization;
- có thể pin revision và kiểm tra SHA-256 trước khi suy luận.

Đây là artifact cộng đồng mới và chưa phải bản phát hành chính thức của tác giả
model gốc. Rủi ro provenance được giảm bằng pin revision, hash, test hành vi và
không cho tự cập nhật model.

## 3. Phạm vi

### 3.1 Có trong feature

- module phục hồi dấu câu độc lập;
- tải model lần đầu, cache local và chạy offline về sau;
- checkbox bật/tắt trong UI, mặc định bật và lưu lựa chọn;
- nối option qua API và pipeline;
- cảnh báo best-effort khi tải/nạp/suy luận thất bại;
- unit test, integration test và kiểm tra invariant timestamp/từ;
- tài liệu về dung lượng, offline, nguồn model và license.

### 3.2 Không có trong feature

- sửa chính tả, thay từ, thêm từ, xóa từ hoặc nối từ;
- thay đổi diarization, glossary, export format hay timestamp;
- nhận diện thêm dấu `!`, `;`, `…` vì model được chọn không công bố các nhãn này;
- chạy punctuation bằng dịch vụ cloud;
- tự tải model mới khi repository upstream thay đổi;
- phục hồi dấu câu cho partial transcript sau khi process chết;
- huấn luyện hoặc fine-tune model ở v1.

## 4. Thành phần và hợp đồng

### 4.1 `app/punctuate.py`

Module mới là biên duy nhất giữa pipeline và runtime/model punctuation.

Interface công khai:

```python
def restore(
    words: list[Word],
    *,
    progress_cb: Callable[[float], None] | None = None,
) -> PunctuationResult:
    ...
```

```python
@dataclass
class PunctuationResult:
    words: list[Word]
    applied: bool
    warning: str | None = None
```

Hợp đồng:

1. `result.words` luôn có cùng độ dài và thứ tự với input.
2. `result.words[i].start == words[i].start` và `end` bằng tuyệt đối.
3. Hàm không mutate input; output dùng các `Word` mới.
4. Khi input rỗng, không load model, trả list rỗng, `applied=False`, không warning.
5. Khi bỏ qua hoặc có lỗi, trả bản sao tương đương input, `applied=False` và warning
   ngắn bằng tiếng Việt; không raise lỗi model ra pipeline.
6. Khi thành công, `applied=True`; text chỉ khác ở casing và dấu `. , : ?`.
7. Model/session được cache tối đa một instance trong process.

Module không import `onnxruntime` hoặc tokenizer ở import time. Dependency nặng được
lazy-import khi feature thật sự bật, để startup, test và luồng tắt punctuation không
chịu chi phí model.

### 4.2 Model registry và cache

`app/config.py` thêm một registry riêng, không trộn với `MODEL_REGISTRY` của ASR:

```python
PUNCTUATION_MODEL = {
    "repo_id": "welcomyou/vibert-capu-onnx",
    "revision": "a7754d037f4a9e29f7f3224f27acb60149eab874",
    "filename": "vibert-capu.int8.onnx",
    "size": 115_707_731,
    "sha256": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
    "license": "CC-BY-SA-4.0",
}
```

Cache đặt tại `data_dir()/punctuation`. Chỉ tải các file runtime cần thiết:

- `vibert-capu.int8.onnx`;
- `vocab.txt`;
- `vocabulary/labels.txt`;
- `config.json`;
- `README.md` để giữ notice nguồn/license cạnh artifact.

Không tải hoặc thực thi Python code từ model repository. ViTranscript tự viết adapter
ONNX nhỏ, có test, và không bật `trust_remote_code`.

Sau download, app kiểm tra size và SHA-256 của ONNX rồi mới ghi marker manifest bằng
atomic replace. `punctuation_is_downloaded()` chỉ trả true khi file và manifest khớp
revision/hash. Artifact sai hash bị coi là chưa hợp lệ và không được nạp.

### 4.3 Dependencies

Thêm trực tiếp:

- `onnxruntime` cho inference CPU;
- `tokenizers` để tạo BERT WordPiece inputs và `word_ids` mà không cần `transformers`.

Không thêm `torch`, `tensorflow`, `transformers` hay code remote. `numpy` và
`huggingface-hub` đã có trong dự án.

Việc chọn version cụ thể và xác minh wheel cho Python 3.10–3.12 trên macOS arm64,
macOS x86_64 và Windows x64 thuộc implementation plan. Lockfile đã tạo phải không có
package `torch` hoặc `tensorflow` trong dependency graph.

### 4.4 Tokenization và ánh xạ 1:1

Mỗi `Word.text` được parse nội bộ thành chuỗi các mảnh nhưng giữ nguyên mapping về
`Word` nguồn:

- whitespace của Whisper;
- một hoặc nhiều lexical token;
- dấu câu thuộc `. , : ?` nếu đã có.

Whitespace được giữ nguyên verbatim. Trường hợp bình thường, một `Word` chứa một
lexical token. Nhánh phòng thủ của `transcribe.py` có thể trả cả segment trong một
`Word` khi faster-whisper không có word timestamps; adapter vẫn xử lý các lexical
token bên trong rồi ráp lại thành đúng một `Word` với timestamp cũ. Dấu câu nội bộ
làm văn bản dễ đọc hơn, nhưng `build_sentences()` chỉ có thể tạo biên tại cuối
`Word`; feature này không suy đoán timestamp để tách một `Word` thành nhiều phần.
Token chỉ gồm dấu câu hoặc text rỗng không đưa vào model và được trả nguyên trạng.

Model nhận danh sách lexical token đã viết thường. Tokenizer dùng `vocab.txt`,
`is_pretokenized=True` và sinh bốn input đúng contract ONNX:

- `input_ids`;
- `attention_mask`;
- `token_type_ids`;
- `input_offsets`, là vị trí subword đầu tiên của từng token.

Adapter giữ mapping riêng từ vị trí model về `(word_index, lexical_piece_index)`.
Dấu câu nội bộ có thể được biểu diễn như pseudo-token để vòng suy luận sau nhìn thấy
ngữ cảnh, nhưng pseudo-token không bao giờ trở thành `Word` mới và không có timestamp.

### 4.5 Lọc action an toàn

Chỉ các action sau được phép tác động lên output:

- `$KEEP`;
- `$APPEND_,`, `$APPEND_.`, `$APPEND_:`, `$APPEND_?`;
- `$TRANSFORM_CASE_CAPITAL`;
- `$TRANSFORM_CASE_UPPER`;
- `$TRANSFORM_CASE_LOWER`;
- các biến thể case theo vị trí có trong label file, gồm
  `$TRANSFORM_CASE_CAPITAL_1` và `$TRANSFORM_CASE_UPPER_-1`.

Mọi action `$MERGE_*`, `$REPLACE_*`, `$DELETE`, `$TRANSFORM_VERB_*`, unknown và
padding bị đổi thành `$KEEP` trước post-process. Adapter không dùng `difflib` để
cố khôi phục một chuỗi đã bị model sửa; thay vào đó, sửa từ bị chặn ngay tại action
classifier nên mapping luôn 1:1.

Model chạy tối đa ba vòng như inference tham chiếu và dừng sớm khi không có safe
action làm thay đổi state. Dấu câu đã tồn tại được ưu tiên; app không tạo `,,`, `..`
hoặc thay dấu câu gốc bằng dự đoán khác. Cuối cùng pseudo-token được gắn lại vào
`Word` đứng trước.

### 4.6 Transcript dài và chunk overlap

Inference dùng chunk 48 lexical word, overlap 12 word, tương thích cấu hình tham
chiếu của model. Với một word xuất hiện ở nhiều chunk, chọn dự đoán từ chunk mà word
nằm xa mép nhất; nếu bằng nhau, chọn chunk có offset nhỏ hơn. Quy tắc này cố định và
phải có unit test để không tạo dấu câu khác nhau theo thứ tự xử lý chunk.

`progress_cb` báo tỷ lệ theo số lexical word đã có dự đoán cuối cùng, không theo số
chunk thô, nên progress tăng đơn điệu từ 0 đến 1.

## 5. Nối vào pipeline

`pipeline.run()` thêm tham số:

```python
enable_punctuation: bool = True
```

Sau `transcribe.transcribe()` và trước diarization/tách câu:

1. nếu tắt, giữ `words` nguyên trạng;
2. nếu bật, gọi `punctuate.restore(words)`;
3. dùng `PunctuationResult.words` cho `segment.build_sentences()`;
4. ghi metadata punctuation vào result;
5. nếu có warning, job vẫn `done` và warning được nối vào note hiện có.

Result bổ sung:

```json
{
  "punctuation": {
    "requested": true,
    "applied": true,
    "backend": "vibert-capu-onnx-int8",
    "warning": null
  }
}
```

Nếu fallback, `applied=false`, `backend` vẫn cho biết backend được yêu cầu và
`warning` mô tả lý do ở mức an toàn. Warning không chứa local path đầy đủ, transcript
hay exception có dữ liệu người dùng; traceback chi tiết chỉ ghi log cục bộ.

Checkpoint `partial.jsonl` tiếp tục ghi word thô ngay khi ASR phát ra. Đây là chủ ý:
checkpoint bảo vệ công sức transcript và không bị phụ thuộc model hậu kỳ. Khi khôi
phục partial sau crash, UI ghi rõ bản partial chưa được phục hồi dấu câu.

### 5.1 Tiến trình

Thang mặc định được cân lại:

| Stage | Phần trăm |
|---|---:|
| Convert | 2–6 |
| Load ASR model | 6–12 |
| Transcribe | 12–66 |
| Download/load/restore punctuation | 66–72 |
| Diarize | 72–92 |
| Finalize | 94–100 |

Nếu một stage bị tắt, progress nhảy qua vùng đó nhưng không lùi. Lần đầu tải model,
message phải ghi rõ đang tải model dấu câu khoảng 110 MB và chỉ cần mạng lần đầu.

## 6. API, settings và UI

### 6.1 Settings

`DEFAULT_SETTINGS` thêm:

```python
"punctuate": True
```

Settings cũ không có key sẽ nhận mặc định `true`. `save_settings()` chỉ lưu boolean
đã chuẩn hóa, không nhận string tùy ý.

### 6.2 API

`POST /api/jobs` thêm form field:

```python
punctuate: Annotated[bool, Form()] = True
```

Server truyền option qua `_run_job()` tới `pipeline.run()`. Việc thêm field là tương
thích ngược: client cũ không gửi field vẫn bật theo default.

`GET /api/meta` bổ sung:

```json
{
  "punctuation": {
    "downloaded": false,
    "size": "~110 MB",
    "license": "CC-BY-SA-4.0"
  }
}
```

### 6.3 UI

Thêm checkbox trong nhóm tùy chọn transcript:

> Tự chèn dấu câu (khuyên dùng cho PhoWhisper)

Checkbox mặc định bật, lấy giá trị đã lưu khi `loadMeta()`, và gửi `true`/`false`
qua `FormData`. Dòng trợ giúp hiển thị “lần đầu tải ~110 MB” hoặc “đã tải” từ meta.

Khi fallback, UI vẫn hiển thị kết quả và note màu cảnh báo:

> Không thể chạy model dấu câu; transcript gốc vẫn được giữ nguyên.

Checkbox tắt phải tạo đúng hành vi legacy: không tải model, không import ONNX Runtime
và không thay đổi word trước `build_sentences()`.

## 7. Error handling

Các lỗi sau đều dùng best-effort fallback:

- không có mạng trong lần tải đầu;
- download thiếu file, size/hash sai;
- tokenizer không nạp được vocab;
- ONNX Runtime không có CPU provider hoặc không tạo được session;
- input/output model sai tên hoặc shape;
- suy luận lỗi ở bất kỳ chunk nào;
- post-process vi phạm invariant.

Nếu một chunk lỗi, toàn bộ bước punctuation fallback về **toàn bộ input gốc**, không
trộn nửa transcript đã sửa với nửa chưa sửa. Trước khi trả kết quả thành công, module
chạy invariant check cuối; sai count, timestamp, thứ tự hoặc lexical content làm
`applied=False` và trả input gốc.

Không bắt mọi exception ở tầng server. `punctuate.restore()` chỉ hấp thụ lỗi thuộc
feature; lỗi core pipeline vẫn theo cơ chế job error hiện tại.

## 8. License, nguồn gốc và phân phối

- Không bundle weight ONNX trong source ZIP, installer hay git repository.
- Model được tải vào data directory ở lần dùng đầu tiên từ revision đã pin.
- README và `THIRD_PARTY_NOTICES.md` ghi tên model, tác giả/repository, nguồn model
  gốc, revision, link và license CC-BY-SA-4.0.
- `README.md` tải cùng artifact được giữ trong cache như notice đi kèm.
- Không copy/vendor `gec_model.py`, `modeling_seq2labels.py` hoặc utility code từ
  repository model; adapter inference là code của ViTranscript.
- Nếu sau này muốn bundle hoặc redistribute weight, phải review lại nghĩa vụ license
  trước khi phát hành. Spec này không đưa ra kết luận pháp lý về sản phẩm thương mại.

## 9. Kiểm thử

### 9.1 Unit tests, không tải model

Dùng fake tokenizer/session/logits để khóa các hành vi:

1. append dấu chấm/phẩy/hai chấm/dấu hỏi đúng word;
2. case transform được áp dụng nhưng lexical spelling/diacritics không đổi;
3. merge/delete/replace/verb action bị bỏ qua;
4. whitespace prefix và dấu câu gốc được giữ;
5. không tạo dấu câu trùng;
6. một `Word` chứa nhiều lexical token được ráp lại mà không đổi timestamp;
7. output count/order/timestamp bất biến và input object không bị mutate;
8. input rỗng không load model;
9. chunk overlap chọn prediction theo quy tắc “xa mép nhất”;
10. progress tăng đơn điệu và kết thúc ở 1;
11. exception hoặc invariant failure trả toàn input gốc cùng warning;
12. session cache chỉ load một lần.

### 9.2 Integration tests, không tải model

- fake punctuation thêm dấu chấm trước `build_sentences()` và làm câu được tách tại
  đúng word;
- pipeline tắt punctuation không gọi loader;
- pipeline fallback vẫn trả job/result thành công;
- server nhận form field, lưu setting và truyền đúng boolean;
- client cũ không gửi field vẫn nhận default bật;
- partial recovery ghi chú chưa phục hồi dấu câu;
- note punctuation được nối với note file dài thay vì ghi đè.

### 9.3 Model smoke, có tải artifact pin

Một test đánh dấu `model`/manual thực hiện trên artifact thật:

- tải đúng revision, xác minh size và SHA-256;
- chạy một đoạn tiếng Việt không dấu câu từ model card;
- output có ít nhất một dấu câu được hỗ trợ và một biến đổi viết hoa;
- invariant lexical word/timestamp vẫn pass;
- chạy lần hai khi tắt mạng vẫn thành công từ cache.

Test này không chạy trong unit suite mặc định và không được giả lập Windows PASS từ
kết quả macOS.

### 9.4 Đánh giá chất lượng biên câu

Trên fixture tiếng Việt 3–5 phút có transcript gõ tay và dấu câu chuẩn:

- biểu diễn mỗi biên câu bằng index word đứng ngay trước biên; một dự đoán khớp khi
  cách biên chuẩn không quá 2 word; mỗi biên chỉ được ghép một lần bằng maximum
  one-to-one matching rồi tính precision, recall và F1;
- điều kiện chấp nhận: bật punctuation tăng ít nhất 10 điểm phần trăm boundary F1;
- lexical WER sau chuẩn hóa bỏ casing/dấu câu phải bằng baseline, vì feature không
  được đổi từ;
- ghi model revision, máy, thời gian và peak RSS cùng kết quả.

Nếu fixture không thể commit vì riêng tư/bản quyền, chỉ lưu transcript đã ẩn danh và
bảng số đo; không đưa audio người dùng vào repository.

## 10. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| PR-01 | Với mọi input, output có cùng count/order/start/end của `Word`. |
| PR-02 | Sau khi bỏ casing và `. , : ?`, lexical content output bằng input. |
| PR-03 | Dấu model thêm xuất hiện trước `build_sentences()` và có thể tạo biên câu. |
| PR-04 | Tắt checkbox tái tạo đúng luồng legacy và không load dependency/model. |
| PR-05 | Lỗi model không làm job fail; người dùng nhận transcript gốc và warning. |
| PR-06 | Lần dùng đầu tải artifact pin; lần sau chạy offline từ cache. |
| PR-07 | Size/hash sai bị từ chối; không nạp artifact không xác minh. |
| PR-08 | Settings/API/UI mặc định bật và lưu lựa chọn người dùng. |
| PR-09 | Partial checkpoint vẫn khôi phục được và được ghi chú là chưa punctuate. |
| PR-10 | Dependency graph không chứa PyTorch hoặc TensorFlow. |
| PR-11 | Model/notice/license được ghi trong README và third-party notices. |
| PR-12 | Unit tests, integration tests, ruff và toàn bộ test hiện có đều pass. |
| PR-13 | Boundary F1 trên fixture tăng ít nhất 10 điểm phần trăm; lexical WER không đổi. |
| PR-14 | Smoke model thật được ghi riêng cho macOS arm64, macOS x86_64 và Windows x64. |

## 11. File map dự kiến cho implementation plan

### Tạo mới

- `app/punctuate.py`
- `tests/test_punctuate.py`
- `THIRD_PARTY_NOTICES.md`

### Sửa

- `pyproject.toml`
- `uv.lock`
- `app/config.py`
- `app/pipeline.py`
- `app/server.py`
- `app/static/index.html`
- `tests/test_core.py`
- `README.md`
- tài liệu task/tracker tương ứng khi implementation bắt đầu

## 12. Thứ tự rollout và rollback

1. Thêm adapter/model cache và test invariant trước khi nối pipeline.
2. Nối pipeline phía server với option mặc định nhưng chưa đổi UI test fixture.
3. Thêm UI/settings/meta và cảnh báo.
4. Chạy unit/integration suite, sau đó mới chạy model smoke có mạng.
5. Đo fixture biên câu và ghi kết quả theo từng nền tảng.

Rollback chức năng chỉ cần tắt checkbox. Nếu phải rollback code, bỏ stage punctuation
không ảnh hưởng schema job cũ; consumer phải coi field `result.punctuation` là tùy
chọn. Cache model có thể để nguyên và được uninstaller/data cleanup xử lý như các
model khác.

## 13. Rủi ro còn lại

| Rủi ro | Giảm thiểu |
|---|---|
| Artifact ONNX là port cộng đồng mới | Pin revision/hash, không auto-update, smoke artifact thật và benchmark. |
| Model viết hoa sai tên riêng | Chỉ cho case action; glossary chạy sau punctuation; người dùng có thể tắt. |
| Dấu câu sai ở biên chunk | Overlap 12, chọn prediction xa mép nhất, test determinism. |
| Tăng thời gian/RAM | INT8 110 MiB, lazy-load, cache một session, ghi benchmark/RSS. |
| Lần đầu offline | Fallback rõ ràng; không làm mất transcript; UI báo cần mạng để tải model. |
| Nghĩa vụ CC-BY-SA-4.0 | Không bundle weight, giữ notice/attribution, review lại trước khi redistribute. |
| Model output/action schema đổi | Revision pin và kiểm tra input/output/label contract trước inference. |

Không còn quyết định sản phẩm mở trong phạm vi spec này. Sau khi người dùng duyệt
file, bước tiếp theo là viết implementation plan chi tiết; chưa triển khai code trong
giai đoạn hiện tại.
