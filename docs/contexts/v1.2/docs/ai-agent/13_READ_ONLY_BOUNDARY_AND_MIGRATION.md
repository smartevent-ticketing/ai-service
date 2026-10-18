# 13 — READ_ONLY Contract & Migration từ Context Pack v1.0

**Đây là tài liệu bắt buộc đọc sau AGENTS.md và có quyền ưu tiên hơn phần kế hoạch cũ.**

## 1. Phát biểu phạm vi chính thức

AI Chatbot SmartEvent là **Trợ lý ĐỌC / PHÂN TÍCH / TƯ VẤN**, không phải tác nhân giao dịch. AI không sở hữu hoặc thực thi quyền tạo, sửa, xóa dữ liệu nghiệp vụ.

### Được phép

- Tìm kiếm sự kiện đã công bố, kiểm tra thông tin và giá từ GET hợp lệ.
- Phân tích inventory/seat snapshot từ endpoint đã audit visibility.
- Xếp hạng phương án vé và giải thích hard/soft constraints.
- Tra cứu đơn hàng, thanh toán, vé, hồ sơ refund-review **của chính người dùng** sau xác thực.
- RAG câu hỏi FAQ, chính sách đã duyệt; JEV đánh giá bằng chứng.
- Lưu trạng thái hội thoại tối thiểu vào namespace riêng (nếu đã chốt retention), chỉ để nhớ yêu cầu người dùng.
- Đưa **liên kết tới màn hình nghiệp vụ có sẵn** cho người dùng tự đặt vé hoặc tự gửi yêu cầu hỗ trợ.

### Tuyệt đối không được phép

- Gọi `POST /api/v1/reservations`, `POST /api/v1/orders`, payment/create-url, POST refund-review, cancel reservation/order, refresh QR, transfer ticket, gửi email, update account, admin actions.
- Thực hiện batch/event/message/webhook/job/background tool để né chặn POST.
- Ghi business database trực tiếp; sửa trạng thái Redis counter của backend; cập nhật business documents/RAG nguồn.
- Tạo các thao tác giả bằng ngôn ngữ như 'Đã giữ vé hộ bạn' nếu chỉ mới gợi ý.

## 2. Ba lớp bảo vệ

| Tầng | Hàng rào |
|---|---|
| Product/Policy | Quy tắc không viết business, action chỉ đọc hoặc điều hướng |
| Tool Executor | Registry GET-only, deny non-GET, static endpoint, auth ownership, kiểm tra side-effect GET |
| Identity/Network | AI service principal/token chỉ có quyền đọc; deny-write backend policy và giới hạn truy cập mạng/DB khi có thể |

**Lưu ý:** Nếu backend hiện không hỗ trợ service principal chỉ đọc, không giả định đã có. Dùng credential user hợp lệ cho endpoint GET, và xây lớp bảo vệ ở BFF/AI; cân nhắc thêm read-only scope ở backend như một nhiệm vụ hạ tầng có test.

## 3. Phân biệt 'sửa dữ liệu hội thoại' và 'sửa nghiệp vụ'

Người dùng nói 'đổi ngân sách thành 1 triệu' → chatbot được cập nhật `budget_amount` **trong dialogue state** để tư vấn chính xác. Đây là trạng thái nội bộ của phiên chat.

Người dùng nói 'đổi đơn hàng thành 2 vé' → chatbot **không** được sửa order/reservation/cart trong Spring Boot. Chỉ hướng dẫn thao tác trên giao diện và cảnh báo quy định.

Cũng phân biệt **Coding Agent** được chủ dự án giao sửa code trên branch (hành động phát triển phần mềm) với **chatbot runtime** không được sửa business data. Không tự áp lệnh 'read-only' để cấm Coding Agent hoàn thành nhiệm vụ code, nhưng cũng không dùng quyền coding để ghi vào production DB.

## 4. Bảng thay thế v1.0 → v1.2

| Mô tả cũ | Điều chỉnh v1.2 |
|---|---|
| `create_reservation` là V2 option | XÓA khỏi registry, roadmap và actions. Không hỗ trợ mọi version |
| `request_refund_review` sau confirmation | XÓA. Chỉ đọc review hiện tại + hướng dẫn UI |
| `prepare_checkout` | Thay `NAVIGATE_TO_BOOKING`; route `/reservations/{eventId}`; không gọi `/checkout` khi chưa có reservation |
| `AWAITING_CONFIRMATION` để làm mutation | Loại khỏi chatbot state machine; hỏi xác nhận chỉ để rõ preference, không cấp quyền ghi |
| 'revalidate trước mutation' | 'GET lại trước khi tư vấn/điều hướng' |
| 'mutation retry/idempotency' | Không có mutation từ AI để retry |
| 'V2 tự giữ chỗ' | Xóa khỏi backlog và future product scope |
| 'refund support tạo hồ sơ' | Chỉ RAG chính sách/GET trạng thái + đường dẫn hỗ trợ |

## 5. Điều kiện nghiệm thu quan trọng

- Không có tool mutation trong YAML, Markdown, prompt, source code AI.
- Test executor từ chối mọi non-GET và endpoint lạ trước network I/O.
- Test tất cả request trực tiếp/gián tiếp (jailbreak, RAG prompt injection, vendor fallback) đều không tạo business write.
- Test GET với unpublished event; không xuất dữ liệu chưa công bố nếu chưa có quyền.
- Integration test với DB test chứng minh một phiên chatbot không làm đổi số lượng/thực thể nghiệp vụ (ngoại trừ user tự làm trong UI riêng).
- UI chỉ hiển thị liên kết hoặc lựa chọn người dùng tự nhấn; không gắn hidden action POST.

## 6. Phần tài liệu ngoài gói đã bị thay thế

Những bản PRD v1.2, Context Pack v1.0, báo cáo/roadmap cũ chỉ có giá trị tham khảo về kiến trúc/đặc tả **không mâu thuẫn READ_ONLY**. Bất kỳ chỗ nào cho chatbot tạo reservation, request refund-review hoặc tự hoàn tất giao dịch đã bị quy tắc này thay thế. AI Agent không sử dụng tài liệu đó như nguồn cho phép mutation.

## v1.2 — Hợp đồng bảo vệ dữ liệu là một phần của READ_ONLY

GET không đồng nghĩa an toàn: response có thể chứa QR/PII, endpoint GET có thể kích hoạt side-effect. READ_ONLY được thực thi bởi allowlist tool-name+path, deny non-GET và side-effect GET, customer-only auth, published-only visibility, *output projection before model*, deny redirects/SSRF, và tests trong tài liệu 14. Mọi private tool và child event tool chưa đạt gate bị disabled. Không lách qua admin/customer BFF, background job hay RAG/LLM vendor. Quy tắc này không thay đổi quyền của người dùng thao tác trên giao diện nghiệp vụ hiện hữu.
