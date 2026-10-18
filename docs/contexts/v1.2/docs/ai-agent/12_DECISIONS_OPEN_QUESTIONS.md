# 12 — Architectural Decisions & Open Questions (v1.2)

## A. Quyết định khóa

- **D-000 — READ_ONLY (ACCEPTED, 18/10/2026):** AI chatbot chỉ GET/read/analyze/recommend/explain, không tạo/sửa/xóa bất kỳ business record nào; toàn bộ V1/V2/V3. Không có ngoại lệ do confirmation.
- **D-001 — AI Service tách repo:** FastAPI service; không nhúng AI orchestration vào Spring Boot modular monolith.
- **D-002 — Backend source of truth:** dữ kiện nghiệp vụ GET từ Spring Boot; không business direct DB. Chat state storage (nếu có) nằm namespace riêng.
- **D-003 — SLM + QLoRA:** thử nghiệm Qwen3-1.7B, model sinh JSON intent/slots/delta/proposed READ action; chỉ giữ adapter nếu cải thiện benchmark.
- **D-004 — Deterministic TODS:** merge state chat, kiểm tra ontology/authorization/deny writes.
- **D-005 — RAG knowledge only:** corpus chính sách/FAQ versioned, approved.
- **D-006 — JEV optional:** routing/evidence, có fallback.
- **D-007 — Ticket Optimizer pure:** lọc hard constraints + ranking; không giữ ghế.
- **D-008 — Navigation only:** `NAVIGATE_TO_BOOKING`, `SHOW_SUPPORT_CHANNEL` chỉ là frontend UI guidance; chatbot không gửi mutation.
- **D-009 — Training target:** 4.000 train + 600 validation + 600 test là kế hoạch đề xuất, chưa chứng minh đủ bằng đánh giá thực nghiệm.
- **D-010 — API allowlist:** chỉ GET, tắt các endpoint con event khi chưa chứng minh unpublished visibility guard.

## B. Những vấn đề còn mở (không được suy diễn thành quyền ghi)

1. Auth BFF cho GET riêng tư: thiết kế verified token forwarding/session exchange.
2. Chat state storage và retention/privacy: Redis ngắn hạn hay PostgreSQL AI-owned. Không cấp quyền business DB ghi.
3. Unpublished event visibility cho `areas`, `ticket-types`, `sale-phases`, `inventory`, `seats`: audit và fix trước khi bật.
4. Retrieval: pgvector hoặc alternative sau benchmark corpus.
5. Fallback LLM, SLO/cost budgets, GPU serving.
6. Availability và giá thành JEV: dùng khi so sánh thực nghiệm chứng minh giá trị.
7. Human support: kênh UI/đường dẫn nào là nguồn được phê duyệt (không tự tạo ticket)?
8. Corpus owner/version/effective dates, data retention.
9. Handoff UI: có cho phép prefill tier/phase/qty tới `/reservations/{eventId}` hay chỉ deep link event? Xác minh route trước khi phát hành.
10. Quy trình review các chỉ dẫn prompt injection trong nội dung sự kiện/FAQ.

## C. Quy tắc thay đổi quyết định

Không Coding Agent nào được tự mở quyền business mutation. Thay đổi D-000 cần quyết định product/security riêng, ADR mới, thay lại rulebook/config/schema/tests/permission và phê duyệt chủ dự án. Trước khi có quyết định đó, mọi tài liệu cũ nhắc tới create_reservation hoặc request_refund_review trong AI tool phải coi là **superseded**.

## v1.2 — Tiến độ phát hiện kiểm toán

- **P1-01 / P1-03:** hợp đồng field allowlist, response/input schema đã thiết kế trong registry; cần implementation và integration test.
- **P1-02:** tất cả private tools đều disabled tới khi có verified customer-self-only path; không kế thừa ADMIN bypass.
- **P1-04:** reference harness và negative tests trong ZIP; integration với FastAPI/HTTP/backend thật chưa có.
- **P1-05:** schema dữ liệu huấn luyện được siết chặt, có negative tests, canonical flat slots.
- **P1-06:** năm tool child-event vẫn disabled; chỉ bật từng cái sau khi có backend visibility tests.
- **P2:** auth forwarding, seat-status filtering, corpus governance, flat state, SHA/run manifest đã thành đặc tả; **triển khai runtime và nghiệm thu còn pending**.

Quyết định **không nới quyền READ_ONLY**. Đây là closure của sai lệch tài liệu/contract, không phải closure của lỗ hổng runtime.
