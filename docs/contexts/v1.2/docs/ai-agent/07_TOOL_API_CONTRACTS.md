# 07 — Hợp đồng READ-ONLY Tool Registry và API

## 1. Quy tắc bắt buộc

**Tất cả business tools do AI gọi phải là GET và không có side-effect.** Không dùng tool POST/PUT/PATCH/DELETE dù 'chưa bật' hoặc 'sẽ bật ở V2'. Backend hiện có quyền tạo/hủy/hoàn tiền cho **UI và người dùng**, nhưng AI hoàn toàn không sử dụng quyền đó.

Mô hình chỉ sinh `proposed_action`/`tool_name` trong allowlist. `ReadOnlyBusinessToolExecutor` xác thực method, path, tham số typed, auth, ownership, timeout, result schema; **deny-by-default**. Không cho model tự tạo URL hoặc truy vấn business DB. Nếu endpoint GET có ghi dữ liệu hoặc chưa kiểm tra public visibility thì chưa cấp phép cho chatbot cho đến khi được audit/fix.

## 2. Công cụ GET công khai (có điều kiện visibility)

| Tool | Backend endpoint | Điều kiện |
|---|---|---|
| `search_events` | `GET /api/v1/events?q=&city=&categoryId=` | Chỉ sự kiện công khai; phân trang đầy đủ/giới hạn rõ. |
| `get_event_details` | `GET /api/v1/events/{id}` hoặc `/slug/{slug}` | Backend bảo vệ draft/unpublished. |
| `get_event_areas` | `GET /api/v1/events/{eventId}/areas` | **Chưa mặc định bật** nếu chưa bảo vệ khu vực của unpublished event. |
| `get_ticket_types` | `GET /api/v1/events/{eventId}/ticket-types` | **Chưa mặc định bật** trước khi audit published-only. |
| `get_sale_phases` | `GET /api/v1/events/{eventId}/sale-phases` | **Chưa mặc định bật** trước khi audit published-only. |
| `get_event_inventory` | `GET /api/v1/events/{eventId}/inventory` | **Chưa mặc định bật** trước khi audit published-only. |
| `get_available_seats` | `GET /api/v1/areas/{areaId}/seats/available` | **Chưa mặc định bật** trước khi audit published-only. |

**Không cấp quyền vì API HTTP là GET một cách máy móc.** Các API liên quan sự kiện phải bảo đảm không lộ cấu hình của sự kiện chưa công bố (cần xác thực ở backend và integration tests). Không lọc `date/budget` trên trang tìm kiếm nhỏ rồi khẳng định không có kết quả.

## 3. Công cụ GET riêng tư — yêu cầu auth và ownership

| Tool | API backend | Ràng buộc |
|---|---|---|
| `get_active_reservation` | `GET /api/v1/reservations/active?eventId=` | Buyer đã xác thực. |
| `get_reservation` | `GET /api/v1/reservations/{id}` | ID thuộc tài khoản. |
| `get_my_orders` | `GET /api/v1/orders/my-orders` | Chỉ tài khoản hiện tại. |
| `get_order` | `GET /api/v1/orders/{id}` | Chặn truy cập chéo. |
| `get_payment_status` | `GET /api/v1/payments/{id}` | Quyền sở hữu ở backend. |
| `get_my_tickets` | `GET /api/v1/tickets/my-tickets` | Không trả QR credential thô cho model. |
| `get_refund_review` | `GET /api/v1/orders/{orderId}/refund-review` | Buyer chính chủ; chỉ đọc. |

BFF truyền auth context đã xác minh theo phương án thiết kế riêng; không tin role cookie hay decode JWT unsigned. Không log token. Không gửi full payload riêng tư sang LLM provider trừ phần tối thiểu thực sự cần và được phép theo policy.

## 4. Công cụ tính toán / tri thức KHÔNG GHI

- `retrieve_policy`: truy xuất bản sao corpus đã được biên tập, lọc access/effective dates; không sửa nguồn tài liệu.
- `optimize_ticket_selection`: hàm thuần trên snapshot, không giữ ghế hoặc trừ tồn kho.
- `compare_events`, `summarize_order_status`: tính toán/phân tích trên dữ liệu đã được cho phép đọc.
- `NAVIGATE_TO_BOOKING`, `SHOW_SUPPORT_CHANNEL`: **UI actions** (không phải backend tool), trả route nội bộ/URL kênh hỗ trợ đã được allowlist để người dùng tự thao tác. Model không sinh URL động.

## 5. Danh sách CẤM — không tồn tại trong registry

`create_reservation`, `cancel_reservation`, `confirm_reservation`, `create_order`, `cancel_order`, `create_payment_url`, `request_refund_review`, `approve_refund`, `transfer_ticket`, `refresh_ticket_qr`, `send_invoice`, `send_notification`, `update_profile`, `create_support_ticket` và mọi alias tương đương.

Không có ngoại lệ 'sau xác nhận' hay 'chỉ V2'. Nếu người dùng yêu cầu, chatbot phải thông báo không có quyền và chỉ dẫn giao diện chính chủ. Không dùng hàng đợi, webhook, batch hoặc worker để thực hiện gián tiếp.

## 6. Handoff sang giao diện đặt vé hiện tại

- Điều hướng sang `/reservations/{eventId}` với query `tier`, `phase`, `qty` (nếu đã xác minh frontend hỗ trợ). Không suy diễn `eventId` từ slug khi cần UUID.
- UI hiện tại `useBookingCart` sẽ validate phase, quota và seat; người dùng **tự** nhấn giữ chỗ.
- `/checkout?reservationId=...` chỉ là màn hình dành cho reservation đã được tạo bởi luồng UI nghiệp vụ; AI không tạo `reservationId`.
- Đề xuất ghế cụ thể không có nghĩa chúng đã được chọn trong giỏ hàng hoặc đã giữ. Dữ liệu `rowName/seatNumber` không tự bảo đảm tọa độ ghế liền nhau.

## 7. Lỗi và retry

Các lỗi: `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `STALE_DATA`, `RATE_LIMITED`, `UPSTREAM_TIMEOUT`, `UPSTREAM_UNAVAILABLE`, `READ_ONLY_DENIED`, `UNKNOWN_ERROR`. GET có thể retry hữu hạn theo policy nếu endpoint không có side-effect. Không retry/hợp thức hóa POST business tool vì tool đó **không được phép tồn tại**.

## 8. Contract check — phải chạy trong CI

1. `tool_registry.yaml`: tất cả method đều `GET` hoặc internal pure computation, tuyệt đối `mutation: true` không hợp lệ.
2. Không có tool tên chứa `create|update|delete|cancel|refund|transfer|payment_url|reserve|hold|submit` biểu thị hành động ghi.
3. Mỗi endpoint có response schema và test authorization/visibility trước khi enable.
4. Test injection yêu cầu model gọi POST phải bị từ chối ở cả policy và executor.
5. Test GET chỉ đọc: so sánh trạng thái nghiệp vụ trước/sau truy vấn trên DB test.

## v1.2 — Hợp đồng cưỡng chế runtime (ƯU TIÊN CAO)

Mọi tool dùng schema và field projection ở `configs/tool_registry.yaml` và tài liệu 14; giá trị `enabled=false` là **chặn thực thi**, không chỉ tắt UI. Public call phải anonymous; private call phải verified CUSTOMER_SELF_ONLY (không cho ADMIN bypass). Không có raw DTO tới bất kỳ model/log/JEV. Tất cả GET chưa audit visibility/ownership đang disabled. Endpoint `/api/v1/areas/{areaId}/seats/available` trả **mọi seat status**, nên chỉ chọn status AVAILABLE. Search ngày/giờ chưa có server-side filter đầy đủ: không lọc một trang rồi nói không có kết quả. ReadOnly reference harness tại `scripts/reference_readonly_executor.py` chỉ dùng để test contract, chưa phải runtime production.
