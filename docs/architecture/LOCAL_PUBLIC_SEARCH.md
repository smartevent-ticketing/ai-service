# Tìm sự kiện công khai ở môi trường local

Luồng: web `localhost:3000` → BFF `/api/chat` → AI `localhost:8001` → backend chạy trên máy ở `8080`. Từ container AI, địa chỉ backend là `http://host.docker.internal:8080`; `127.0.0.1` bên trong container chỉ trỏ chính container đó.

## Chuẩn bị và kiểm chứng

Backend và hạ tầng dự án cần chạy sẵn. Build `bootJar` của repository backend hiện tại. Image `smartevent-backend:local` cung cấp Java 17 để chạy JAR này trong môi trường thử, không dùng database ứng dụng.

Trong repository AI, chạy PowerShell 7:

```powershell
docker build -t smartevent-ai-service:local-public-search .
./scripts/verify-public-search.ps1
```

Script tạo network, PostgreSQL và Spring backend thử riêng, không công bố cổng mạng của các dịch vụ thử. Migration khởi tạo database thử; fixture thêm 25 sự kiện công khai và các sự kiện nháp/chờ duyệt/đã hủy. Các consumer của backend thử được tắt. AI thử chỉ gọi HTTP GET, không nhận thông tin kết nối database.

Kiểm tra live bao gồm: tìm kiếm ẩn danh, lọc thành phố/từ khóa, loại bản nháp, phân trang không trùng, giới hạn công cụ, chặn GET có tác dụng ghi và loại trường ngoài allowlist. Trình chạy độc lập đối chiếu SHA-256 của toàn bộ dòng dữ liệu trong database thử trước/sau. Chỉ khi các kiểm tra đạt và hai digest trùng nhau, script mới tạo cấu hình triển khai trong `artifacts/local-public-search/configs`. Dữ liệu nghiệp vụ không được ghi vào báo cáo. Container và network thử được dọn sau khi chạy.

Thư mục kết quả phải mới để giữ nguyên bằng chứng cũ. Khi kiểm chứng lại, dùng `-OutputDirectory artifacts/local-public-search-<ten-moi>` và đặt `AI_REVIEWED_CONFIG_DIR` trỏ tới thư mục `configs` mới khi chạy Compose. Script Python từ chối bằng chứng thiếu, digest khác, mã nguồn đã thay đổi hoặc có HTTP không thuộc GET `/api/v1/events`.

Các trạng thái `PASS` trong cấu hình này chỉ áp dụng cho luồng tìm sự kiện công khai đã thử. Cấu hình gốc dưới `configs/` và bản đóng gói dưới `resources/` giữ nguyên mặc định tắt. Những công cụ khác, dữ liệu tài khoản và RAG không được bật bởi cấu hình local.

## Chạy AI

```powershell
docker compose -f docker-compose.local.yml up -d
```

Nếu đã có container `smartevent-ai` được tạo thủ công, dừng và đổi tên container cũ trước khi chạy Compose để giữ một bản quay lui. Compose gắn cấu hình đã kiểm chứng ở chế độ chỉ đọc và không tự tạo thư mục cấu hình bị thiếu. `BACKEND_BASE_URL` được cấu hình riêng cho Docker trong Compose, không làm thay đổi mặc định khi chạy Python trực tiếp trên máy.

Frontend dùng `AI_SERVICE_URL=http://127.0.0.1:8001` ở phía server (đây cũng là mặc định hiện có). Không đưa biến này vào `NEXT_PUBLIC_*`. Kiểm tra `/health/ready` của AI: danh sách công cụ được bật chỉ có `search_events`. Các phần chưa được nghiệm thu có thể làm trạng thái tổng vẫn là `degraded`.

## Phạm vi câu trả lời

Bot liệt kê tên, thành phố và giờ diễn ra từ dữ liệu công khai đã qua projection. Thời gian hiển thị theo UTC+7; không tự sinh giá hay tồn kho. Danh sách rỗng được phân biệt với một phần kết quả chưa đọc hết.

Phản hồi tìm kiếm còn có `event_links` gồm `event_id`, `title`, `slug` lấy từ các dòng backend đã qua projection, tối đa 10 sự kiện. Frontend tạo nút “Xem sự kiện” bằng route nội bộ `/events/{slug}`, không lấy URL từ nội dung câu trả lời. Chức năng này thuộc lớp ứng dụng, không đòi hỏi huấn luyện lại mô hình.

Workspace hiện dùng cấu hình đã kiểm chứng lại ở `artifacts/local-public-search-event-links/configs`; lựa chọn được lưu bằng `AI_REVIEWED_CONFIG_DIR` trong `.env` để lần chạy Compose tiếp theo tiếp tục dùng đúng cấu hình.

Bản gia cố tiếp theo chuyển cấu hình đang phục vụ sang `artifacts/local-chatbot-hardening/configs`, bổ sung corpus hướng dẫn được chủ dự án duyệt. Xem [báo cáo và cách vận hành bản hiện tại](CHATBOT_HARDENING_2026_10_30.md). Các cấu hình search-only cũ vẫn được giữ làm bằng chứng, không phải cấu hình đang dùng.

Các sự kiện `DRAFT` của bộ seed vẫn bị ẩn. Muốn thấy chúng trong chat, người tổ chức/admin phải thực hiện luồng công bố trong giao diện. Không tự sửa trạng thái chỉ để có kết quả demo.

API tìm kiếm backend hiện hỗ trợ từ khóa, thành phố và danh mục, chưa có bộ lọc ngày. Với câu hỏi như “cuối tháng này”, bot nói rõ bộ lọc thời gian chưa được áp dụng rồi hiển thị ngày của từng kết quả. Đây vẫn là baseline theo luật; LLM/QLoRA và tư vấn vé theo tồn kho chưa được tích hợp.

## Kiểm tra trên workspace ngày 30/10/2026

Đã chạy lint, kiểm tra kiểu cho 46 file nguồn, kiểm tra kiến trúc/cấu hình và 245 test (coverage 93,34%). Docker image được build và kiểm tra qua backend Spring Boot/PostgreSQL thử độc lập; digest dữ liệu trước/sau trùng nhau. Cấu hình local đã được triển khai ở cổng 8001. Kiểm tra lại câu hỏi qua BFF web `/api/chat` trả `grounding=BACKEND_READ`, `tool_called=search_events` và 2 sự kiện công khai ở Hồ Chí Minh tại thời điểm kiểm tra. Chỉ `search_events` được bật. Các container/database thử đã được dọn; database ứng dụng không bị sửa trạng thái sự kiện.
