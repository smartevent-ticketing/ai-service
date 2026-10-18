# Corpus FAQ và chính sách khởi tạo — BẢN NHÁP

Bộ tài liệu tiếng Việt được xây dựng theo yêu cầu chủ dự án ngày 18/10/2026,
dựa trên code foundation và đặc tả READ_ONLY. Đây là nội dung khởi tạo để review,
không phải bằng chứng Product/Legal đã phê duyệt chính sách công ty.

Các câu trả lời về khả năng của trợ lý được đối chiếu mã nguồn. Không tự đặt ra
thời hạn hoàn tiền, mức phí, điều kiện đổi vé, cam kết thanh toán hoặc thời gian
xử lý yêu cầu mà backend/tài liệu chính thức chưa chứng minh.

| Tệp | Nội dung | Nguồn đối chiếu |
|---|---|---|
| `01_gioi_han_tro_ly.md` | Quyền hạn trợ lý | ADR-001, gateway, response composer |
| `02_tim_su_kien_va_ton_kho.md` | Tìm sự kiện và giới hạn dữ liệu | Chat use case, page projection, release gates |
| `03_hoi_thoai_va_du_lieu.md` | State, ngữ cảnh và thông tin tài khoản | HTTP DTO, dialogue domain, READ_ONLY contract |
| `04_hoan_tien_va_ho_tro.md` | Cách xử lý câu hỏi hoàn tiền khi thiếu chính sách | Response composer, corpus governance |
| `05_huong_dan_thao_tac.md` | Hướng dẫn người dùng tự thực hiện giao dịch | READ_ONLY boundary và composer |

`manifest.draft.json` ghi hash và trạng thái `draft`, với phần phê duyệt/thời hiệu
để trống. Nó chủ động không phải catalog ingest hợp lệ. Muốn phục vụ nguồn thật:

1. Chủ nội dung xác minh với luồng web/backend đang triển khai và chốt từng nội dung.
2. Người được ủy quyền ghi hồ sơ phê duyệt, version, audience và thời hiệu thực tế.
3. Tạo catalog theo schema runtime; pin checksum catalog sau khi review.
4. Build bằng tokenizer được pin; đánh giá câu hỏi/nguồn chuẩn và kiểm thử quyền.
5. Publish artifact; review trust anchors và các gate trước khi bật runtime.

Không đổi tên bản nháp hoặc fixture thành `PRODUCTION` để bỏ qua bước phê duyệt.
Các tài liệu này không chứa URL hỗ trợ giả định. Chỉ bổ sung canonical URL của
SmartEvent khi đã được chủ nội dung xác nhận; định danh `approved://` trong manifest
là định danh nguồn, không phải địa chỉ website để người dùng truy cập.
