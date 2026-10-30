# Demo hai model PEFT luân phiên trên GPU

NLU Qwen2.5-1.5B và RAG Qwen2.5-3B dùng chung một bộ điều phối. Khi cần đổi
model, bộ điều phối chờ suy luận hiện tại kết thúc, bỏ tham chiếu model/tokenizer
cũ, thu gom đối tượng và trả bộ nhớ cache CUDA rồi mới nạp model tiếp theo.
Không giữ một bản trọng số dự phòng trên RAM. Hai model dùng NF4 4-bit và được
đặt trên GPU số 0; không tự phân tán sang CPU. Nếu tiếp tục dùng cùng model,
nó được giữ lại để tránh nạp lại không cần thiết.

## Chạy trên Windows

Đứng tại thư mục `ai-service`, dùng PowerShell. Dừng API model cũ bằng Ctrl+C
trong cửa sổ của nó trước khi khởi động demo. Chỉ chạy một tiến trình, một worker,
không dùng `--reload`.

```powershell
# Kiểm tra cả hai adapter và model nền local, không nạp GPU.
.\scripts\local\run_sequential.ps1 -Mode check

# Tùy chọn: chạy NLU -> RAG -> NLU, ghi thời gian và bộ nhớ GPU.
.\scripts\local\run_sequential.ps1 -Mode smoke

# Chuẩn bị corpus hướng dẫn đã được duyệt, chạy kiểm thử corpus/HTTP.
# Không cần Docker/backend; không bật tìm sự kiện bằng lệnh này.
.\scripts\local\run_sequential.ps1 -Mode prepare

# Sau khi prepare thành công, khởi động API.
.\scripts\local\run_sequential.ps1
```

Mở `http://127.0.0.1:8001/docs`, dùng `POST /api/v1/chat`. Ví dụ câu tìm kiếm
`Tìm giúp tôi 2 vé ở Hà Nội.` dùng NLU; câu `Có những phương thức thanh toán nào?`
có thể đi qua NLU, truy hồi corpus rồi gọi model RAG. Chưa có bằng chứng tìm kiếm
backend thì sự kiện vẫn trả `NO_LIVE_DATA`; đó không phải lỗi nạp model.

`prepare` chỉ dùng năm tài liệu có checksum và hồ sơ duyệt hiện có, không tạo
phê duyệt mới. Nó dùng baseline rule/extractive để kiểm tra corpus và không
nạp GPU. Đầu ra mặc định là `artifacts/local-sequential-help`. Nếu thư mục đã
tồn tại, launcher tự dùng tên mới có thời gian, giữ nguyên bản cũ. Chỉ sau khi
build và toàn bộ kiểm tra đạt, nó mới lưu lựa chọn vào
`artifacts/local-sequential-help-current.json`. Lệnh serve không có `-ConfigDir`
sẽ đọc lựa chọn thành công gần nhất và kiểm tra lại bằng chứng.
Một lần prepare thất bại không thay đổi lựa chọn trước. Có thể chỉ định nơi xuất:

```powershell
.\scripts\local\run_sequential.ps1 -Mode prepare -HelpOutput artifacts/local-sequential-help-v2
.\scripts\local\run_sequential.ps1 -ConfigDir artifacts/local-sequential-help-v2/configs
```

Launcher từ chối cấu hình chưa có báo cáo nghiệm thu corpus, báo cáo cũ so với
source, hết hạn, kiểm tra không đạt, công cụ khác được bật hoặc corpus không
còn hợp lệ. Có thể cung cấp `-ConfigDir` trỏ tới cấu hình help/search đã được
nghiệm thu độc lập; việc đổi model không tự mở gate. Mặc định tất cả business
tool vẫn tắt. File `.env`, cấu hình gốc và trọng số model không bị sửa.

Đổi vị trí cache bằng `-BaseModelPath` cho NLU và `-RagBaseModelPath` cho RAG.
Script chỉ đọc model nền local, không tải hoặc huấn luyện lại.

## Quan sát và thời gian chờ

`GET /health/ready` có `model_runtime.mode=sequential`, `active_model`, `switches`,
`operations` và `last_operation_seconds`. `nlu_startup=ready` xác nhận probe khởi
động đã đạt; sau khi đổi sang RAG, NLU không còn nằm trên GPU. Log ghi tên model
và thời gian, không ghi nội dung hội thoại.

Chế độ demo dùng deadline 180 giây cho mỗi giai đoạn NLU/RAG. Deadline thông
thường vẫn là 12/15 giây. Khi request timeout, thread suy luận có thể còn chạy;
bộ điều phối vẫn giữ khóa để request sau không gỡ model đang được dùng.
Shutdown giải phóng model cuối cùng. Bộ nhớ do ứng dụng khác chiếm không thuộc
quyền quản lý của pool.

Giao diện web hiện có giới hạn BFF 30 giây, nên demo luân phiên này nên thử trực
tiếp qua Swagger/API. Chưa sửa timeout hoặc xác nhận luồng web cho chế độ này.

## Kết quả thực tế ngày 30/10/2026

Chuỗi kiểm tra đã chạy thật bằng hai adapter local trên RTX 2050 4 GB:

| Bước | Thời gian gồm nạp/suy luận | PyTorch allocated sau bước | PyTorch reserved sau bước |
|---|---:|---:|---:|
| NLU lần đầu | 21,231 giây | 1.179 MiB | 1.278 MiB |
| Đổi sang RAG | 24,047 giây | 2.085 MiB | 2.310 MiB |
| Đổi lại NLU | 10,652 giây | 1.179 MiB | 1.270 MiB |

Đạt `SEQUENTIAL_MODEL_SMOKE_OK`, ba bước đều `mode=model`, hai lần đổi model.
Kiểm tra sau mỗi bước xác nhận provider không hoạt động không giữ model hoặc
tokenizer. Đây là số đo một lần, không phải thời gian bảo đảm; không phải số
đo đỉnh bộ nhớ hoặc toàn bộ VRAM của GPU. Câu hỏi cần cả NLU và RAG phải cộng
thời gian hai giai đoạn. Câu chỉ cần NLU không phải nạp model RAG.

Smoke dùng đoạn văn `DEMO_INPUT` để kiểm tra thực thi model, không bật corpus
hoặc cấp quyền nghiệp vụ. Model RAG vẫn có thể thêm nội dung ngoài bằng chứng;
verifier hiện tại có thể chuyển câu trả lời sang `extractive_fallback`. Không
bỏ kiểm tra nguồn để ép hiện câu sinh.

Nhóm kiểm tra cục bộ đạt 67 ca, gồm khóa giữa hai luồng, giải phóng tham chiếu,
thu gom trọng số trong traceback lỗi, fallback sau lỗi, timeout wiring và từ
chối cấu hình/bằng chứng sai. Ruff, mypy và kiểm tra kiến trúc/cấu hình đạt.

Trong phiên agent, bước prepare dừng vì kiểm thử không hoàn tất trong 40 giây;
cấu hình tạo dở đã được tắt và giữ riêng để chẩn đoán. Chưa có profile corpus
PASS mới, chưa nghiệm thu HTTP/E2E của chế độ luân phiên. Cần chạy prepare bằng
PowerShell thông thường trước khi phục vụ corpus qua API.

Muốn quay lại NLU GPU + RAG trích xuất: dừng demo rồi chạy
`.\scripts\local\run_peft.ps1` như trước.

## Sửa lỗi prepare không nhận được bằng chứng thanh toán

Câu “Làm thế nào để thanh toán” và “Còn MoMo thì sao?” từng tìm đúng chunk qua
BM25 nhưng bị bộ đánh giá loại vì tính từ trong cấu trúc câu hỏi vào mức khớp.
Đã bỏ các cụm hỏi hoàn chỉnh ở đầu/cuối câu trước khi đánh giá, giữ nguyên ngưỡng
0,5. Với câu đã bỏ cụm hỏi, toàn bộ từ chủ đề còn lại phải có trong bằng chứng;
không biến ApplePay chưa có nguồn hoặc chủ đề lạc đề thành câu trả lời có nguồn.
Tài liệu, checksum phê duyệt và kiểm tra injection/thu hồi/hết hạn vẫn giữ nguyên.
Đã bổ sung kiểm tra tái dựng corpus cho cả 17 câu chuẩn bị và định tuyến hội thoại.
