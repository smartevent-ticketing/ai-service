# Corpus FAQ và chính sách khởi tạo — BẢN NHÁP

Bộ tài liệu tiếng Việt được cập nhật theo xác nhận của chủ dự án ngày 18/10/2026,
đối chiếu code foundation và đặc tả READ_ONLY. Xác nhận trong cuộc trao đổi là đầu
vào biên tập; chưa thay thế bản chính sách được công bố trên website SmartEvent.
Nội dung vẫn là bản nháp, chưa có hồ sơ duyệt, URL canonical hoặc ngày hiệu lực.

Các câu trả lời về khả năng của trợ lý được đối chiếu mã nguồn. Không tự đặt ra
mức phí, điều kiện chuyển vé chi tiết, thời hạn xử lý, cam kết thanh toán hoặc
kết quả hỗ trợ chưa được xác nhận. Bản điều khoản là dự thảo để đưa lên web, không
phải kết luận đã đáp ứng mọi yêu cầu pháp lý của một website đang vận hành.

## Quyết định nội dung đã được chủ dự án xác nhận

- Phạm vi bao gồm chính sách chung và quy định riêng của sự kiện/nhà tổ chức.
- Khách hàng không được hủy hoặc hoàn vé theo yêu cầu thay đổi nhu cầu tham dự.
- Bản hiện tại hỗ trợ VNPAY Sandbox; sự cố báo trừ tiền/chưa nhận vé được khách
  tự gửi biểu mẫu hỗ trợ để admin kiểm tra, không phải chatbot gửi thay.
- SmartEvent cho phép chuyển vé. Check-in xuất trình QR, không bắt buộc đúng tên
  người mua; không suy ra điều kiện chuyển vé chỉ từ cách check-in.
- Kênh hỗ trợ là biểu mẫu trên website; phần báo cáo sự cố sẽ được cập nhật thêm.
- Chỉ nội dung được công bố trên website SmartEvent mới là nguồn chuẩn của sản phẩm.

## Những nội dung còn chờ xác nhận hoặc công bố

- Tên miền chính thức, URL điều khoản, URL biểu mẫu hỗ trợ và các trang sự kiện.
- Quy tắc ưu tiên khi quy định riêng và chung mâu thuẫn; hiện ghi nhận chưa chốt.
  Khi chưa có căn cứ, không tự chọn nguồn để kết luận; hướng dẫn gửi form hỗ trợ.
- Phí/thời hạn/số lần chuyển, điều kiện người nhận và trạng thái QR sau chuyển.
- Cách xử lý sự kiện hủy/hoãn/thay đổi, thời hạn phản hồi và kết quả khắc phục.
- Đơn vị vận hành, người chịu trách nhiệm, người duyệt, hồ sơ duyệt và thời hiệu.

Giới hạn không hoàn/hủy được biên tập cho trường hợp khách thay đổi nhu cầu,
không biến thành điều khoản loại bỏ mọi trách nhiệm đối với lỗi giao dịch/dịch vụ
hoặc quyền lợi bắt buộc theo pháp luật. Căn cứ rà soát điều khoản: Điều 25 Luật
Bảo vệ quyền lợi người tiêu dùng 19/2023/QH15, xem [Công báo Chính phủ](https://congbao.chinhphu.vn/van-ban/luat-so-19-2023-qh15-39843/45917.htm).
Nguồn VNPAY dùng để đối chiếu thuật ngữ môi trường thử nghiệm, không cấp quyền
gọi API thanh toán/hoàn tiền: [tài liệu VNPAY](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html).
Các nguồn pháp luật/kỹ thuật này là tham chiếu biên tập, không thay thế URL
chính sách SmartEvent và không tự được thêm vào corpus trả lời sản phẩm.

## Danh mục bản nháp

| Tệp | Nội dung | Nguồn đối chiếu |
|---|---|---|
| `01_gioi_han_tro_ly.md` | Quyền hạn trợ lý | ADR-001, gateway, response composer |
| `02_tim_su_kien_va_ton_kho.md` | Tìm sự kiện và giới hạn dữ liệu | Chat use case, page projection, release gates |
| `03_hoi_thoai_va_du_lieu.md` | State, ngữ cảnh và thông tin tài khoản | HTTP DTO, dialogue domain, READ_ONLY contract |
| `04_hoan_tien_va_ho_tro.md` | Không hoàn/hủy do đổi ý, VNPAY Sandbox và form hỗ trợ | Xác nhận chủ dự án, READ_ONLY boundary |
| `05_huong_dan_thao_tac.md` | Chuyển vé, check-in QR và người dùng tự thao tác | Xác nhận chủ dự án, READ_ONLY boundary |
| `06_dieu_khoan_su_dung.md` | Dự thảo điều khoản để biên tập và đưa lên web | Các xác nhận nêu trên; còn thiếu mục công bố |

`templates/event_policy.template.md` chỉ là mẫu biên tập quy định riêng, không
có dữ liệu của sự kiện thật, không nằm trong danh sách nguồn và không được ingest.
Metadata/runtime hiện chưa có event_id/organizer_id để lọc phạm vi. Cần triển
khai và kiểm thử ranh giới giữa hai sự kiện trước khi bật trả lời quy định riêng.

`manifest.draft.json` ghi hash và trạng thái `draft`, với phần phê duyệt/thời hiệu
để trống. Nó chủ động không phải catalog ingest hợp lệ. Muốn phục vụ nguồn thật:

1. Chủ nội dung xác minh với luồng web/backend, hoàn thiện từng nội dung và công
   bố trên website SmartEvent; ghi URL canonical thật, phạm vi và phiên bản áp dụng.
2. Người được ủy quyền ghi hồ sơ phê duyệt, version, audience và thời hiệu thực tế.
3. Tạo catalog theo schema runtime; pin checksum catalog sau khi review.
4. Build bằng tokenizer được pin; đánh giá câu hỏi/nguồn chuẩn và kiểm thử quyền.
5. Publish artifact; review trust anchors và các gate trước khi bật runtime.

Không đổi tên bản nháp hoặc fixture thành `PRODUCTION` để bỏ qua bước phê duyệt.
Các tài liệu này không chứa URL hỗ trợ giả định. Chỉ bổ sung canonical URL của
SmartEvent khi đã được chủ nội dung xác nhận. `canonical_uri` trong draft manifest
để null cho đến khi có trang công bố thật; không dùng `approved://` thay thế yêu
cầu nguồn chính thức trên web. Không ingest README, mẫu biên tập hoặc ghi chú duyệt.
