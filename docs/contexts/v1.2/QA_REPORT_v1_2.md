# SmartEvent AI Agent Context Pack v1.2 — QA và điều kiện phát hành

**Kiểm tra ngày 18/10/2026.** Từ v1.1 READ_ONLY + báo cáo kiểm toán v1.1. Snapshot mã nguồn repo nêu tại `docs/ai-agent/17_REPOSITORY_SOURCE_SNAPSHOT.md`.

## Đã thực hiện trong gói này

- Bổ sung typed `arguments_schema`, `response_schema`, `response.fields` projection cho 14 GET tools. Các backend raw DTO không được chuyển thẳng tới model.
- Cấm QR (`qrCodeBase64`), ticket code/owner IDs, URL thanh toán, token, raw PII khỏi projection. `get_my_tickets` vẫn ở trạng thái disabled chờ runtime gate.
- Khóa toàn bộ private chatbot tools vào `CUSTOMER_SELF_ONLY`, enabled false cho đến khi có verified BFF/backend identity/ownership.
- Năm child-event GET tools vẫn disabled để tránh truy xuất dữ liệu chưa công bố khi backend chưa chứng minh guard.
- Thêm testable reference executor (injected fake transport) cấm unknown tool, side-effect GET, redirect, encoded path, extra args, elevated ADMIN, raw QR/PII.
- Ràng buộc schema dataset v1.2: 21 intents, typed delta oneOf, flat slots, secondary intents hợp lệ, `scenario_family` và `dialogue_group`.
- Thêm RAG source approval/efficacy/audience governance và schema manifest, benchmark SHA reproducibility, machine-readable implementation gates.
- Đồng bộ AGENTS.md, Markdown đặc tả, prompts coding/audit, README, manifest.

## Kết quả hiện tại

| Kiểm tra | Kết quả |
|---|---|
| `python -m pytest -q tests` | **47 passed** |
| `python scripts/validate_readonly_pack.py` | **PASS** (static) |
| DOCX accessibility audit | **0 high / 0 medium / 0 low** |
| A4 PDF | **44 trang**, không trang trống; kiểm tra bounds text: **0 warning** |
| ZIP validation | `testzip() is None` |

## Chưa được xác minh / Release blocker

- Chưa có AI runtime production để thử live zero-write; executor là reference harness và không gửi HTTP thật.
- Chưa chạy full backend integration tests: unpublished event child, customer A/B/Admin và payment/order ownership.
- Chưa có verified Next.js Chat BFF private token delegation.
- Chưa có tài liệu RAG policy approved/effective từ chủ dự án; không tự làm giả corpus.
- Chưa có model fine-tuned, kết quả benchmark, GPU latency/load/penetration test.

**Status:** `DESIGN_AND_REFERENCE_TESTS_READY; RUNTIME_RELEASE_BLOCKED`.
Không được tự bật các tool disabled để demo tính năng, không tuyên bố an toàn production chỉ từ kiểm thử mock.
