# Chạy model hiện có bằng PEFT trên Windows

Không cần huấn luyện lại để sử dụng hai adapter đã xuất. Đã thử nạp riêng NLU
1.5B và RAG 3B trên RTX 2050 ngày 30/10/2026. Một ca thử không xác nhận chất
lượng toàn bộ model; RAG 3B còn cần đánh giá độ đúng và trích dẫn.

Từ thư mục `ai-service`, chạy trong PowerShell:

```powershell
# Kiểm tra đường dẫn, chưa nạp GPU.
.\scripts\local\run_peft.ps1 -Mode check

# Nạp NLU thật, kiểm tra intent/city/quantity; fallback sẽ báo thất bại.
.\scripts\local\run_peft.ps1 -Mode smoke

# Khởi động API, một worker để tránh nạp nhiều bản model.
.\scripts\local\run_peft.ps1
```

Mở `http://127.0.0.1:8001/docs`, gọi `POST /api/v1/chat` với:

```json
{"message":"Tìm giúp tôi 2 vé ở Hà Nội."}
```

Script dùng tokenizer/adapter trong `models/unpacked_nlu_1.5b` và model nền
đã cache tại Hugging Face. Nó không tải model từ mạng, không gọi Ollama,
không đổi `.env` hoặc thiết lập hệ thống. Nếu cache đặt ở vị trí khác, có thể
gọi Python với `--base-model-path` trỏ đến thư mục model nền đầy đủ.

Profile chỉ bật NLU PEFT trong tiến trình con; RAG giữ chế độ extractive.
Các gate và quyền nghiệp vụ dùng nguyên cấu hình repo. Nhận diện được ý định
không đồng nghĩa đã tra cứu backend hoặc đã có corpus được duyệt.

Với GPU 4 GB, chưa bật đồng thời model NLU 1.5B và model sinh RAG 3B. Bước
tiếp theo cho RAG là đánh giá prompt/citation trên corpus được duyệt và xử lý
bộ kiểm tra câu trả lời; không bỏ verifier để ép hiển thị câu sinh. Hai adapter
này không thay thế model embedding phục vụ pgvector.

## Bước 1: nạp sẵn trước khi nhận câu hỏi

Launcher đặt `NLU_PRELOAD=true`. API nạp trọng số và chạy một lần suy luận qua
đúng provider trong ASGI lifespan, trước thông báo `Application startup complete`.
Việc import ứng dụng không nạp GPU. Nạp lỗi hoặc probe trả `fallback` sẽ làm
startup thất bại; không báo model sẵn sàng. Sau startup, `/health/ready` có
`nlu_startup=ready`, `last_nlu_mode=model`, `nlu_availability=available`.

Nếu API cũ đang chạy, dừng bằng Ctrl+C ở cửa sổ của nó rồi chạy lại launcher
để nhận mã mới. Chạy một worker, không dùng `--reload`. Warmup nằm ngoài giới
hạn 12 giây của mỗi câu hỏi; câu hỏi dài vẫn có thể vượt giới hạn suy luận.

## Bước 2: nghiệm thu tìm kiếm rồi dùng cấu hình riêng

Thực hiện bằng PowerShell 7 trên máy có quyền Docker. Backend thật cần chạy
với cấu hình dự án hiện có ở `http://127.0.0.1:8080`, sử dụng JAR mới. Bộ nghiệm
thu dưới đây tạo database thử riêng, không nạp fixture vào database ứng dụng.

Trước tiên build và kiểm thử backend trong thư mục `smartevent-backend`:

```powershell
.\gradlew.bat test postgresTest bootJar --no-daemon
```

Chỉ tiếp tục sau khi lệnh thành công. Trong thư mục `ai-service`:

```powershell
docker build -t smartevent-backend:local ..\smartevent-backend
docker build -t smartevent-ai-service:local-public-search .
.\scripts\verify-public-search.ps1 -OutputDirectory artifacts/peft-public-search-verified
```

Chỉ sau khi nghiệm thu in ra đường dẫn cấu hình mới, khởi động API:

```powershell
.\scripts\local\run_peft.ps1 `
  -SearchConfigDir artifacts/peft-public-search-verified/configs `
  -BackendBaseUrl http://127.0.0.1:8080
```

Launcher kiểm tra bằng chứng, fingerprint mã AI/fixture/script, SHA-256 của
backend JAR và quyền trong cấu hình; từ chối bằng chứng cũ, JAR khác, source
backend mới hơn JAR hoặc cấu hình đã bị mở rộng. Sau đó thử một GET tìm kiếm
tới backend thật trước khi nạp GPU. Việc đối chiếu JAR local không chứng minh
tiến trình backend đang chạy chính JAR đó; người vận hành phải khởi động lại
backend bằng bản đã nghiệm thu trước khi dùng cấu hình này.

Trong cửa sổ PowerShell khác, kiểm tra đúng tiến trình API đang phục vụ:

```powershell
.\scripts\local\run_peft.ps1 -Mode verify
```

Lệnh `verify` không nạp thêm model. Nó yêu cầu startup PEFT đã xong, chỉ có
`search_events` được bật và quyền lọc ngày/giá đã được kiểm chứng. Sau đó gửi
một câu tìm kiếm qua HTTP và yêu cầu `mode=model`, `tool_called=search_events`,
`grounding=BACKEND_READ`, trạng thái `OK` hoặc `EMPTY`. Kết quả rỗng hợp lệ
không bị trình bày như lỗi model. Thành công in `MODEL_BACKEND_HTTP_OK`.

Bộ nghiệm thu backend kiểm tra thành phố/từ khóa, phân trang, sự kiện chưa
công bố, khoảng ngày `[startFrom, startBefore)` với UTC và offset `+07:00`,
giá `<`/`<=`, ngân sách tổng chia số vé, evidence giá trên thẻ, loại vé/đợt bán
không hoạt động, hết vé, chưa mở bán/hết hạn và liên kết khu vực/tồn kho sai
sự kiện. So sánh digest database thử trước/sau và chỉ cho phép HTTP GET đúng
`/api/v1/events`. Gate `PUBLISHED-CHILD` trong profile chỉ áp dụng cho giá/ngày
của `search_events`, không nghiệm thu các API chi tiết/khu vực/ghế khác.

Cấu hình gốc và bản đóng gói vẫn tắt công cụ. Mỗi lần chạy nghiệm thu phải dùng
thư mục output mới; không sửa report cũ hoặc chép trạng thái PASS bằng tay.
Đổi mã nguồn/JAR cần nghiệm thu lại. Bỏ `-SearchConfigDir` để quay về NLU PEFT
với tìm kiếm tắt. RAG vẫn extractive và không được bật bằng profile tìm kiếm.

## Kết quả kiểm tra trong phiên chỉnh sửa

- 41 test unit/hợp đồng cục bộ đạt, gồm startup trực tiếp không dùng socket,
  từ chối fallback, bằng chứng cũ, cấu hình mở rộng và HTTP probe giả lập.
- Ruff, định dạng, mypy (58 file), static architecture guard và đồng bộ
  cấu hình đạt; wheel build đạt. Kiểm tra đường dẫn launcher đạt, chưa nạp thêm
  model trong phiên này.
- Hai file Java vừa sửa biên dịch thành công bằng dependency cache, 22 test
  trọng tâm backend đạt qua JUnit/MockMvc với Mockito Java agent. Đây không phải
  kiểm thử PostgreSQL cho truy vấn mới hoặc HTTP qua mạng.
- TestClient/kiểm thử HTTP thật bị chặn bởi quyền socket của phiên agent
  (`WinError 10013`); Docker API trả permission denied. Chưa tạo profile PASS
  mới và chưa xác nhận model nối backend thật thành công.
- Gradle wrapper bị chặn ghi lock trong cache người dùng. Kiểm thử PostgreSQL
  và thực thi truy vấn HQL mới còn cần chạy trên môi trường có quyền phù hợp.

Các kiểm tra trên không thay thế benchmark model hoặc nghiệm thu toàn stack.
