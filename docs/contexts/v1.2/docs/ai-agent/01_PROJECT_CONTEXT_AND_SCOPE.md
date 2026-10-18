# 01 - Bối cảnh, mục tiêu và phạm vi dự án

## 1. Bối cảnh

SmartEvent là nền tảng quản lý sự kiện và phân phối vé điện tử. Backend hiện đã giải quyết các luồng khó của hệ thống bán vé: sự kiện, phân khu/ghế, hạng vé và đợt mở bán, giữ chỗ có thời hạn, đơn hàng, thanh toán, phát hành vé, QR/check-in, hóa đơn, thông báo bất đồng bộ và hỗ trợ đối soát hoàn tiền.

Chatbot mới không được xây như một hệ thống bán vé song song. **Tại mọi phiên bản, AI chỉ đọc và phân tích; không tạo, sửa, xóa hoặc kích hoạt trạng thái nghiệp vụ.** Mục tiêu là tạo một **lớp tương tác thông minh phía trên hệ thống hiện có**.

## 2. Mục tiêu sản phẩm

SmartEvent AI Ticketing Copilot phải giúp khách hàng:

1. Diễn đạt nhu cầu bằng tiếng Việt tự nhiên.
2. Tìm sự kiện theo địa điểm, danh mục, thời gian và từ khóa.
3. Hiểu giá, đợt bán, hạng vé và tình trạng khả dụng.
4. Đưa ra phương án vé phù hợp theo số lượng, ngân sách và ưu tiên ghế.
5. Đề xuất phương án thay thế khi lựa chọn ban đầu không còn khả dụng.
6. Trả lời FAQ/chính sách bằng nguồn tài liệu đã phê duyệt.
7. Tra cứu dữ liệu cá nhân như order/payment/ticket khi đã xác thực.
8. Chỉ **điều hướng người dùng** tới màn hình chọn vé/đặt vé hiện hữu; người dùng tự thao tác, AI không giữ chỗ.
9. Chỉ **giải thích quy trình hoàn tiền** và hiển thị tình trạng hồ sơ hiện có (nếu được quyền); tuyệt đối không khởi tạo hồ sơ review.

## 3. Điểm mới kỹ thuật chính

Điểm mới không phải “dùng chatbot” hay “dùng RAG”. Trọng tâm là:

**Availability-Aware, Constraint-Aware Conversational Ticket Recommendation**.

Nghĩa là chatbot phải giữ được yêu cầu nhiều lượt, phân biệt hard/soft constraints, lấy dữ liệu tồn kho hiện thời, tối ưu phương án và xử lý stale data trước khi hiển thị hoặc chuyển người dùng sang màn hình giao dịch; chatbot không tiến hành giao dịch.

## 4. Phạm vi V1

### Bắt buộc

- Hội thoại tiếng Việt nhiều lượt.
- Intent + slot + state delta có cấu trúc.
- Tìm kiếm/chi tiết sự kiện.
- Tra cứu ticket type, sale phase, inventory, available seats.
- Ticket Optimizer.
- RAG cho FAQ/policy.
- Tra cứu my orders, payment status, my tickets sau auth.
- `NAVIGATE_TO_BOOKING`: trả gợi ý route nội bộ đến UI đặt vé hiện có; không phải tool và không tạo reservation.
- Logging/tracing tối thiểu, rate limit, validation, fallback.
- Bộ đánh giá chất lượng và dataset riêng.

### Có thể bật sau khi V1 ổn định

- JEV routing/evidence evaluator.
- Không có: khả năng chatbot tự tạo giữ chỗ, kể cả khi người dùng đồng ý. Đây là điều cấm toàn phiên bản.
- Model routing giữa SLM và LLM lớn.

## 5. Ngoài phạm vi V1

- Mọi thao tác ghi nghiệp vụ: tạo/hủy giữ chỗ, tạo đơn, thanh toán, gửi refund-review, chuyển/đổi vé, cập nhật hồ sơ.
- Autonomous payment.
- Automatic refund.
- Multi-agent architecture.
- Reinforcement learning cho dialogue policy.
- Voice-first assistant.
- Personalization dài hạn dựa trên behavioral profiling.
- Recommendation ML phức tạp dựa trên lịch sử click/mua.
- Kubernetes/high-availability production cluster.

## 6. Đối tượng người dùng

### Customer/Buyer - đối tượng chính V1

Use cases: khám phá sự kiện, chọn vé, hỗ trợ booking, order/payment/ticket support.

### Organizer/Admin

Chatbot nghiệp vụ cho organizer/admin **không thuộc V1**. Các quyền này vẫn dùng workspace hiện có. Không expose tool quản trị cho assistant customer.

## 7. Tiêu chí thành công sản phẩm

- Tỷ lệ hoàn thành tác vụ end-to-end >= 85% trên bộ kịch bản chuẩn.
- Không có cross-account leak trong test.
- Không có **bất kỳ AI-triggered business write nào** trong test; tool allowlist chỉ GET đã được kiểm chứng.
- Không có hard-constraint violation trong recommendation test.
- Không hallucinate giá/tồn kho/payment status khi thiếu backend evidence.
- Có benchmark chứng minh QLoRA hoặc JEV đáng được giữ nếu triển khai.
