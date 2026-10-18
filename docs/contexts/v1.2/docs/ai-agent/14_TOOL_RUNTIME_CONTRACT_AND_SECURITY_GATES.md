# 14 — Tool Runtime Contract v1.2 & Security Gates (NORMATIVE)

**Phạm vi:** runtime SmartEvent AI Chatbot chỉ đọc và phân tích. Đây là hợp đồng *thiết kế cần triển khai*, KHÔNG phải tuyên bố đã có executor chạy production. Source of truth machine-readable: `configs/tool_registry.yaml` + `configs/assistant_policy.yaml`.

## A. Trust boundary và thứ tự cưỡng chế

1. Chỉ chấp nhận **tên tool chính xác** tồn tại trong registry; unknown/alias/encoded key bị từ chối *trước mọi I/O*.
2. Nếu `enabled: false`, từ chối luôn; không tự bật khi user yêu cầu hay model phỏng đoán.
3. Method phải `GET` **và** endpoint phải đúng đường tĩnh của một read-safe tool. `GET` không đồng nghĩa an toàn: loại `/api/v1/payments/vnpay/ipn`, `/return`, các đường refresh/verify kích hoạt side-effect và redirect; không cho model tự cung cấp URL.
4. Validate tham số theo JSON Schema `arguments_schema` (UUID, page 0..9, size giới hạn, extra field cấm). URI path không cho encoded slash, `..`, query injection hoặc host ngoài allowlist.
5. Transport nội bộ: backend host từ cấu hình server; timeout 3 s; không follow redirect; không retries ngầm. Chuyển lỗi 401/403/404/429/5xx thành mã có cấu trúc, không yêu cầu model đoán hoặc retry không kiểm soát.
6. Public tools **anonymous**, không chuyển JWT/Admin/service token. Private tools chỉ hoạt động sau gate `PRIVATE-SELF-AUTH`, quyền `CUSTOMER_SELF_ONLY`: token do BFF xác minh/ngữ cảnh session hợp lệ, backend tự xác thực và enforce ownership; deny Admin bypass; không sử dụng `userId` từ prompt.
7. Mọi HTTP response đi qua **allowlist projection trước khi vào bất cứ model, JEV, RAG prompt, log hay analytics nào**. Không chuyển dữ liệu JSON thô, kể cả debug. Unknown key mặc định bị loại.
8. Business fields không ghi vào AI-owned DB. Chỉ có thể lưu conversation state tối thiểu theo retention và quyết định privacy.

## B. Projection đặc biệt

- `get_my_tickets`: chỉ danh sách metadata cần thiết để trả lời, ví dụ `id, eventId, eventName, areaName, seatCode, ticketTypeName, salePhaseName, status, issuedAt, usedAt`. **Cấm** `qrCodeBase64`, `ticketCode`, `currentOwnerUserId`, `originalBuyerUserId`, raw QR, token hashes, URL truy cập bí mật.
- `get_order`/`get_payment_status`: loại PII, `customerNote`, `paymentUrl`, buyer ID, tài liệu nhạy cảm. Tạm **disabled** vì read API cho ADMIN có quyền bypass owner — AI customer không được kế thừa. Backend cần cung cấp customer-safe read path hoặc kiểm soát customer principal và test A/B/Admin.
- `get_available_seats`: endpoint tên available nhưng hiện trả **mọi** trạng thái. Adapter chỉ giữ `status == AVAILABLE`, giới hạn kết quả, giữ thời gian snapshot và thông báo availability có thể thay đổi.
- `search_events/get_event_details`: chỉ xuất `PUBLISHED`, request phải anonymous; mọi text from backend là untrusted data, không được diễn giải như system instruction.
- `get_event_areas/get_ticket_types/get_sale_phases/get_event_inventory/get_available_seats`: mặc định disabled đến khi endpoint parent/child có guard visibility published-only được kiểm thử. **Không được lách bằng cách kiểm tra event PUBLISHED ở AI rồi gọi child GET với event/area ID do model cung cấp nếu backend guard còn thiếu**.
- `get_refund_review`: chỉ status, amount, id/time, không chuyển `reason/evidenceReference/resolutionNote` vào model.

## C. Mở tính năng theo bằng chứng

| Gate | Tiêu chuẩn PASS | Tác động |
|---|---|---|
| PUBLIC-SEARCH | Anonymous public events thật sự chỉ `PUBLISHED`; filter trước pagination; response projection test | Cho bật `search_events` |
| PUBLIC-DETAIL | Event unpublished trả 404/403 cho anonymous; no elevated creds | Cho bật `get_event_details` |
| PUBLISHED-CHILD | Child GET từng loại kiểm tra parent PUBLISHED; area belongs to event; inactive/hidden data không hiển thị; unit/integration tests | Mở từng child tool, không bật cùng lúc thiếu bằng chứng |
| PRIVATE-SELF-AUTH | Verified BFF identity to backend, reject admin principal in customer-chat path; customer A/B tests; 401/403 controlled; projection test | Cho bật từng private tool |
| SAFE-TICKETS | No QR/token/code trong input LLM, JEV, response logs, analytics; fail-closed if DTO changes | Cho bật `get_my_tickets` nếu PRIVATE gate đạt |
| RUNTIME-READONLY | Spy asserts zero write network requests, side-effect GET blocked, redirects/SSRF/canonicalization blocked, business DB snapshot unchanged | Đủ điều kiện release read-only |

## D. Hợp đồng dữ liệu trả về

Với mỗi tool, registry khai báo `response.envelope=ApiResponse.data`, `result_shape`, `fields`, `response_schema`, `max_results` và điều kiện lọc. Adapter phải map `PageResponse` theo OpenAPI thực tế, kiểm tra checksum schema; nếu cấu trúc API đổi phải **fail closed**, không trả raw result để model tự phân tích.

Với API công khai phân trang, backend phải **lọc đúng điều kiện trước pagination**. Search theo ngày chưa được hỗ trợ đúng mức ở controller nguồn; không filter 10 record đầu rồi nói không có kết quả.

## E. Quy tắc thực thi và chứng minh

Mã minh họa kiểm thử: `scripts/reference_readonly_executor.py`. Chỉ là *reference harness với injected fake transport*, không tự cấp quyền production, không thay FastAPI implementation. Test `tests/test_runtime_security_contract.py` phải pass; khi viết runtime thật cần test tương đương ở adapter gắn HTTP client thật/Testcontainers, dùng database snapshot và customer role contracts.

## F. Gate registry là dữ liệu máy đọc

Dùng `configs/implementation_gates.yaml`, `configs/auth_delegation_contract.yaml` và `configs/rag_corpus_policy.yaml` để kiểm tra trạng thái feature gate. Không tự diễn giải một tuyên bố documentation DONE thành gate runtime đã PASS.
