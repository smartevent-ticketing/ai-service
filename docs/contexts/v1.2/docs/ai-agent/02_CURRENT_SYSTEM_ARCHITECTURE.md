# 02 - Kiến trúc SmartEvent hiện tại

**Ranh giới AI v1.2:** các controller POST/PUT/PATCH/DELETE dưới đây thuộc chức năng SmartEvent do người dùng/frontend nghiệp vụ vận hành; chúng **không** phải tool cho AI Chatbot. Không nhầm mô tả backend với quyền thực thi AI.

## 1. Snapshot repository

Tại thời điểm 17/10/2026:

| Repository | Trạng thái / vai trò |
|---|---|
| `smartevent-backend` | Backend nghiệp vụ đang hoạt động; Java 17, Spring Boot 4.0.7, modular monolith |
| `smartevent-web` | Next.js 16.3.2, React 19.2.8, TypeScript, Tailwind 4, openapi-fetch |
| `smartevent-infra` | Docker Compose cho PostgreSQL 16, Redis 7, RabbitMQ 3, MinIO |
| `ai-service` | Repository trống; đây là nơi triển khai chatbot |

## 2. Kiến trúc backend

Backend là **modular monolith**. Các module chính trong `src/main/java/com/smartevent/modules/`:

- `identity`: user, role, JWT, refresh token.
- `event`: category, venue, event, area, seat, media.
- `ticketing`: ticket type, sale phase, inventory, quota/counter.
- `reservation`: giữ chỗ có thời hạn, giữ/nhả resource.
- `ordering`: order, order item, price snapshot.
- `payment`: payment, gateway callback/IPN, reconciliation/refund review.
- `ticket`: phát hành ticket, QR, transfer, check-in.
- `invoice`: invoice, PDF, delivery.
- `outbox`: transactional outbox và publisher worker.
- `notification`: consumer/gửi email.
- `storage`: MinIO object + metadata.

## 3. Source of truth và consistency

- PostgreSQL quyết định state nghiệp vụ.
- Redis chỉ cache/counter/rate-limit; không được dùng làm authority cuối cùng.
- RabbitMQ có semantics at-least-once; consumer phải idempotent.
- MinIO chứa object; PostgreSQL chứa metadata.
- Side effect ngoài DB không nằm trong cùng transaction nên dùng outbox/retry/reconciliation.

## 4. Các state enum quan trọng

### EventStatus
`DRAFT -> PENDING_APPROVAL -> PUBLISHED`, cùng `CANCELLED`, `COMPLETED`.

### SeatStatus
`AVAILABLE`, `HELD`, `SOLD`, `BLOCKED`.

### ReservationStatus
`PENDING`, `CONFIRMED`, `EXPIRED`, `CANCELLED`.

### OrderStatus
`PENDING_PAYMENT`, `PAID`, `CANCELLED`, `EXPIRED`, `PARTIALLY_REFUNDED`, `REFUNDED`.

### PaymentStatus
`INITIATED`, `PENDING`, `SUCCESS`, `FAILED`, `CANCELLED`, `REFUNDED`.

### TicketStatus
`ISSUED`, `USED`, `CANCELLED`, `REFUNDED`, `RESALE_LISTED`, `TRANSFERRED`.

### SalePhaseStatus
`DRAFT`, `SCHEDULED`, `ACTIVE`, `PAUSED`, `CLOSED`, `SOLD_OUT`.

### RefundReviewStatus
`REQUIRED`, `IN_REVIEW`, `REFUNDED_CONFIRMED`, `CLOSED_NO_REFUND`.

Lưu ý: RefundReview là **manual reconciliation state**; không có giá trị nào tự gọi provider refund.

## 5. Concurrency invariants

Agent phải giữ các bất biến sau:

1. Ghế chỉ được chuyển `AVAILABLE -> HELD` bằng thao tác nguyên tử/conditional update.
2. Reservation expiry và payment confirmation có thể chạy đua; chỉ một transition được thắng.
3. Check-in chỉ `ISSUED -> USED` một lần.
4. `affectedRows == 0` trong CAS có thể là business outcome bình thường.
5. Không thay các pattern này bằng read-then-write.

## 6. Frontend hiện tại

Các feature quan trọng:

- `src/features/catalog`: tìm kiếm và chi tiết sự kiện.
- `src/features/booking`: chọn hạng vé/ghế, active reservation, checkout.
- `src/features/orders`: order và refund review.
- `src/features/payments`: payment flow/result.
- `src/features/account`: ticket, invoice, transfer, QR.
- `src/features/auth`: session/login/register.

Client API dùng `openapi-fetch` và generated `src/lib/api/schema.d.ts`.

Access token được giữ phía client memory; refresh token là httpOnly cookie ở Next.js auth route. Vì vậy chatbot không được giả định BFF có thể suy ra user identity chỉ từ role cookie. Với tool riêng tư, authorization token phải được chuyển qua luồng đã xác minh và Spring Boot vẫn phải validate ownership.

## 7. Hạ tầng local

`smartevent-infra/docker-compose.yml` chạy:

- PostgreSQL 16.
- Redis 7.
- RabbitMQ management.
- MinIO.

Port mặc định bind `127.0.0.1`. Flyway trong backend là nguồn schema chuẩn.

## 8. Quality baseline hiện có

Backend đã có unit/service tests và Testcontainers cho một số phạm vi, nhưng tài liệu test-strategy lưu ý coverage hạ tầng/E2E/concurrency thật vẫn cần được mở rộng. Không dùng “số lượng test” để tuyên bố production-ready.

## 9. Nguồn code agent phải kiểm tra khi tích hợp AI

- `smartevent-backend/docs/01-architecture/system-architecture.md`
- `smartevent-backend/docs/01-architecture/architecture-decisions.md`
- `smartevent-backend/docs/01-architecture/critical-flows.md`
- `smartevent-backend/src/main/java/com/smartevent/config/SecurityConfig.java`
- Controllers/DTOs của event, ticketing, reservation, ordering, payment, ticket.
- `smartevent-web/src/lib/api/client.ts`
- API wrappers trong `src/features/*/api`.
- `smartevent-web/AGENTS.md` trước mọi thay đổi frontend.
