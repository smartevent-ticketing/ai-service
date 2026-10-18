# AGENTS.md — SmartEvent AI Chatbot | READ-ONLY BUSINESS DATA

**Phiên bản 1.2 — 18/10/2026 — READ_ONLY + SAFE DATA PROJECTION + CUSTOMER SELF ONLY**

> **LUẬT CAO NHẤT:** SmartEvent AI Chatbot chỉ được **đọc, tìm kiếm, tổng hợp, giải thích, phân tích và đề xuất** dựa trên dữ liệu có quyền truy cập. AI Chatbot và bất kỳ tool/worker nào do chatbot kích hoạt **không được tạo, sửa, xóa, giữ chỗ, gửi yêu cầu, đặt hàng, chuyển vé, tạo thanh toán, hoàn tiền hoặc thay đổi trạng thái nghiệp vụ**. Mọi yêu cầu ghi dữ liệu phải chuyển người dùng sang giao diện nghiệp vụ có sẵn để **người dùng tự thao tác**; AI không âm thầm thực hiện thay.

Phạm vi lệnh cấm: **toàn bộ các phiên bản V1/V2/V3** cho đến khi có thay đổi quyết định được chủ dự án phê duyệt bằng tài liệu mới; không được suy diễn quyền ghi từ các tài liệu cũ hoặc tính năng backend đã tồn tại.

## 1. Phân biệt hai loại AI Agent

- **Chatbot runtime / AI Service / SLM / LLM / JEV / RAG / Tool Executor:** ràng buộc **READ_ONLY** đối với toàn bộ dữ liệu và hành động nghiệp vụ SmartEvent.
- **Coding Agent / Audit Agent** được giao phát triển dự án: được thay đổi **mã nguồn, tài liệu và test trong nhánh phát triển** theo yêu cầu chủ dự án; không được sử dụng quyền của chatbot để sửa dữ liệu nghiệp vụ thật. Khi kiểm thử chức năng ghi ở backend hiện có, chỉ dùng sandbox/test fixtures tách biệt với dữ liệu thật.
- Trạng thái hội thoại do hệ thống chat sở hữu (`conversation_id`, `state_delta`, lựa chọn UI, cache ngắn hạn) có thể được duy trì theo chính sách riêng để vận hành hội thoại. Đây **không phải** quyền ghi vào event/ticket/order/payment hay bất kỳ bảng nghiệp vụ nào. Nếu phải lưu thông tin hội thoại, tuân thủ chính sách retention/privacy và tách biệt quyền kết nối.

## 2. Kiến trúc cố định

`Next.js Chat UI → Chat BFF → FastAPI AI Service → TODS + SLM (QLoRA thử nghiệm) + RAG + JEV tùy chọn + Ticket Optimizer → READ-ONLY Tool Registry → Spring Boot GET APIs`.

- Spring Boot/PostgreSQL là nguồn sự thật cho event, ticket type, sale phase, inventory, seat, reservation, order, payment, ticket, refund-review.
- Model không tự sinh dữ kiện giá/tồn kho, không tính toán thay backend, không truy cập business DB trực tiếp.
- Ticket Optimizer **chỉ xếp hạng các lựa chọn**; không tạo giữ chỗ.
- RAG trả lời chính sách từ corpus đã duyệt; không tra payment/order bằng RAG.
- JEV chỉ phân loại và đánh giá bằng chứng, tùy chọn, có fallback.
- Mọi đầu ra hành động là **nút điều hướng/khuyến nghị UI**, không phải yêu cầu giao dịch.

## 3. Các bất biến READ_ONLY — vi phạm là P0

1. Tool Registry của chatbot **không có** `POST`, `PUT`, `PATCH`, `DELETE` hay lệnh tác động trạng thái nghiệp vụ. `POST /api/chat` là phương tiện gửi câu hỏi tới chính AI Service, **không phải** tool nghiệp vụ và không cấp quyền ghi.
2. Không cho phép tên tool như `create_reservation`, `request_refund_review`, `create_order`, `cancel_reservation`, `create_payment_url`, `transfer_ticket`, `refresh_qr`, `approve_refund` hoặc wrapper/alias dẫn tới nghiệp vụ tương tự; **không giữ dưới dạng 'disabled trong V1'**.
3. `prepare_checkout` nếu được nhắc trong tài liệu cũ **không phải tool**: thay bằng `NAVIGATE_TO_BOOKING` — chỉ trả `route` nội bộ cho frontend, tối đa gợi ý `eventId`, `ticketTypeId`, `salePhaseId`, `quantity` làm UI prefill theo hợp đồng hiện có. Không gọi API giữ chỗ và không mở `/checkout` khi chưa có `reservationId` từ luồng giao diện chính.
4. Không cho phép chuyển thao tác nghiệp vụ thành background job, webhook, event, SQL, batch, workflow hoặc gọi API gián tiếp.
5. Tool Executor phải allowlist **(GET + path tĩnh đã kiểm chứng + schema validate)**, từ chối mọi method khác và dùng credential backend tối thiểu quyền read-only. GET có side-effect phải được loại trừ khi phát hiện.
6. Với API riêng tư: credential được xác thực, Spring Boot kiểm tra ownership; không tin role, userId hoặc orderId do model tự khai.
7. Không sử dụng API không được backend kiểm tra phạm vi công khai để tiết lộ dữ liệu event chưa xuất bản; phải bổ sung guard backend hoặc adapter filter đã chứng minh đủ.
8. Chỉ hiển thị snapshot tồn kho/ghế với thời gian cập nhật; không bảo đảm còn chỗ tới lúc người dùng đặt vé. Không tuyên bố 'đã giữ/đã mua/đã thanh toán' nếu chưa có chứng cứ GET từ backend.
9. Các câu 'giữ vé giúp', 'hủy đơn giúp', 'hoàn tiền cho tôi' phải dẫn tới **giải thích giới hạn + điều hướng trang nghiệp vụ**, tuyệt đối không thao tác thay.
10. Không đưa token, QR credential, password, thông tin thanh toán nhạy cảm, PII chưa được phép vào prompt, dữ liệu huấn luyện hoặc log.
11. Mọi cấu hình tool/ontology/action/schema/evaluation phải nhất quán với `READ_ONLY`.

## 4. Thứ tự nguồn sự thật

**Quyền hạn và phạm vi sản phẩm:** AGENTS.md v1.2 → `13_READ_ONLY_BOUNDARY_AND_MIGRATION.md` → configs v1.2 → docs 01–12. **Các tài liệu PRD v1.2 / Context Pack v1.0 bị thay thế ở những phần cho phép mutation.** Không chọn quyền ghi dựa trên bản cũ.

**Hiện trạng backend/frontend:** code ở commit/branch đang làm → Flyway/tests → OpenAPI hiện có → ADR hiện hành → README → tài liệu cũ. Phải xác minh mã và hợp đồng cụ thể trước khi tích hợp.

## 5. Các điều kiện bảo mật v1.2 (P1 BẮT BUỘC)

- `GET` không đồng nghĩa an toàn: `/api/v1/payments/vnpay/ipn` là GET có side effect và **không có trong allowlist**.
- Trả lời từ GET không được chuyển raw DTO vào model/JEV/log. Bắt buộc allowlist projection, loại QR `qrCodeBase64`, `ticketCode`, secrets, PII/owner IDs, `paymentUrl`.
- Quyền private chatbot chỉ `CUSTOMER_SELF_ONLY`; không chuyển elevated role ADMIN/service, không sử dụng userId do model khai.
- Chỉ bật tool sau gate có test: public PUBLISHED guard, child visibility, private auth ownership, safe tickets projection, runtime zero-write.
- JSONL theo schema `dataset_contract=1.2`; chỉ flat ontology slots. RAG corpus phải approved/effective, chưa đủ nguồn thì không bịa.
- Xem tài liệu `14_TOOL_RUNTIME_CONTRACT_AND_SECURITY_GATES.md`, `15_RAG_CORPUS_GOVERNANCE.md`, `16_REPRODUCIBILITY_EVALUATION_MANIFEST.md` và `17_REPOSITORY_SOURCE_SNAPSHOT.md`; đồng thời đọc `configs/implementation_gates.yaml`, `configs/auth_delegation_contract.yaml`, `configs/rag_corpus_policy.yaml`.
- Đây là **hợp đồng tài liệu/kiểm thử tham chiếu**, chưa có bằng chứng AI Service runtime đã triển khai. Trạng thái release phải `BLOCKED` cho tới khi integration gates pass.

## 6. Giao thức coding/audit agent

1. Đọc `README_FIRST.md`, `AGENTS.md`, `13_READ_ONLY_BOUNDARY_AND_MIGRATION.md` và file chuyên đề.
2. Xem repo, branch, commit, `git status`; không ghi đè thay đổi chưa hiểu.
3. Lập plan, liệt kê file liên quan, policy/contract, migration và kiểm thử.
4. Không thêm tool nghiệp vụ ghi ở bất kỳ giai đoạn nào. Test chặn mọi phương thức khác GET ở Tool Executor (ngoại trừ transport nội bộ `/chat`).
5. Chạy lint, typecheck, unit, integration, security/evaluation liên quan; với frontend chạy `npm run check`.
6. Khi thấy xung đột, ưu tiên `READ_ONLY`, tạo finding và chỉnh lại cùng PR.
7. Báo cáo rõ thay đổi, bằng chứng, test, rủi ro và các vấn đề còn mở; không tuyên bố production-ready/merge-ready khi chưa chạy gate.

**Lưu ý repo:** `ai-service` là repo trống tại thời điểm khảo sát; chưa có AI production. `smartevent-web/AGENTS.md` cũng phải được đọc trước khi sửa Next.js; file đó chứa quy tắc version-specific.
