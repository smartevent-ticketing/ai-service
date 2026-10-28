# Mẫu biên tập quy định riêng của sự kiện / nhà tổ chức

Trạng thái: TEMPLATE — KHÔNG INGEST, KHÔNG CÔNG BỐ NGUYÊN MẪU NÀY.
Mẫu không đại diện cho bất kỳ sự kiện hoặc nhà tổ chức có thật nào.

## Thông tin cần điền từ nguồn được xác nhận

- Tên và định danh sự kiện; tên và định danh nhà tổ chức.
- Phạm vi: một sự kiện cụ thể hay các sự kiện được liệt kê của cùng nhà tổ chức.
- Tiêu đề trang và URL canonical trên website SmartEvent đã được xác nhận.
- Phiên bản, thời điểm công bố, thời điểm bắt đầu/kết thúc hiệu lực nếu có.
- Người chịu trách nhiệm nội dung, người rà soát và hồ sơ duyệt.
- Quan hệ với chính sách chung: điều khoản nào bổ sung/khác biệt; căn cứ được duyệt.

## Nội dung cần được chủ sự kiện xác nhận

- Điều kiện tham dự/check-in, thời gian, địa điểm và thông tin vé áp dụng.
- Điều kiện chuyển vé: phạm vi, thời hạn, phí nếu có và hướng dẫn trên web.
- Cách tiếp nhận sự cố thanh toán/nhận vé qua biểu mẫu hỗ trợ.
- Cách xử lý khi sự kiện hủy, hoãn hoặc thay đổi; chưa có thông báo thì để chưa chốt.
- Thông tin còn thiếu hoặc mâu thuẫn cần gửi quản trị viên xác nhận.

## Kiểm tra trước khi tạo nguồn corpus

Không điền giả định về tuổi, giấy tờ, phí, thời gian xử lý, quyền hoàn tiền hoặc
quy tắc ưu tiên. Nguồn phải đã được công bố trên website SmartEvent và gắn đúng
định danh/phạm vi. Cần bổ sung hỗ trợ lọc scope ở runtime và đánh giá chéo hai sự
kiện trước khi cho phép retrieval quy định riêng; metadata của runtime hiện tại
chưa có event_id/organizer_id, nên mẫu này không tự tạo khả năng đó.
