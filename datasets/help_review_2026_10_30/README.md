# Bộ hướng dẫn công khai đề nghị duyệt cho demo local

Trạng thái: **chủ dự án đã duyệt dùng cho demo local** trong hội thoại Codex ngày 30/10/2026. Hồ sơ [approval.json](approval.json) khóa SHA-256 của đúng năm tài liệu đã xem. Việc duyệt nội dung không tự bật runtime; cần build, đánh giá và cấu hình riêng.

Đây là nội dung hướng dẫn thao tác được đối chiếu với mã nguồn hiện tại, không bổ sung điều kiện thương mại hoặc chính sách hoàn tiền.

| Tài liệu | Nội dung chính | Nguồn đối chiếu |
|---|---|---|
| [Phương thức thanh toán](01_payment_methods.md) | Bản hiện tại chỉ tích hợp VNPay; không xác nhận giao dịch cá nhân | `PaymentServiceImpl`, `VNPayGatewayProvider`, giao diện thanh toán |
| [Hướng dẫn đặt vé](02_booking_guide.md) | Người dùng chọn sự kiện/vé/ghế và tự thực hiện giao dịch | Giao diện chi tiết sự kiện, giỏ vé và thanh toán |
| [Tìm sự kiện](03_event_search.md) | Chỉ sự kiện công khai, hỗ trợ thành phố/từ khóa, nói rõ giới hạn lọc ngày/giá | `EventRepository`, `EventQueryService`, `ChatUseCase` |
| [Tài khoản và vé](04_ticket_account_help.md) | Đăng nhập để xem dữ liệu cá nhân; không cam kết điều kiện hoàn tiền | Trang tài khoản, ranh giới READ_ONLY của dự án |
| [Ảnh sự kiện](05_organizer_images.md) | JPG/PNG/WebP, 10 MB, ảnh bìa tối thiểu 1080 × 608, chỉnh khi nháp | `EventMediaServiceImpl`, cấu hình multipart, `banner-dimensions` |

Phạm vi xin duyệt: đưa đúng năm tài liệu này vào corpus **hướng dẫn demo local**, có nguồn dẫn trong câu trả lời. Không đưa năm bản nháp cũ vào phục vụ và không tuyên bố hệ thống sẵn sàng production. Người duyệt có thể yêu cầu thay đổi từng tài liệu trước khi bật.
