# SmartEvent AI Ticketing Copilot — Agent Context Pack v1.2 (READ_ONLY)

**Ngày cập nhật:** 18/10/2026. **Trạng thái:** Đã chốt hướng AI chatbot chỉ đọc và phân tích nghiệp vụ; phần đánh giá QLoRA/JEV/hiệu năng vẫn là kế hoạch thử nghiệm, không phải kết quả đã đo.

## Điểm mới bắt buộc so với v1.0

- Chatbot **không được ghi/sửa/xóa** event, ticket, inventory, seat, reservation, order, payment, refund-review, user hoặc tài liệu nghiệp vụ.
- **Xóa** toàn bộ tool mutation khỏi registry (kể cả trạng thái `enabled_in_v1: false`).
- `NAVIGATE_TO_BOOKING` là **ý định hướng dẫn giao diện**, không phải business tool và không phải `prepare_checkout` gọi backend.
- Không có lộ trình V2/V3 'mở quyền đặt vé tự động' theo bộ tài liệu này.
- Xây explicit `ReadOnlyBusinessToolExecutor`: deny non-GET, deny unknown path, deny side-effect, timeout, token minimization, audit.
- Phiên chat có state/cache **nội bộ phục vụ hội thoại**; không dùng quyền đó làm cớ ghi dữ liệu nghiệp vụ.

## Thứ tự đọc

1. `AGENTS.md` — luật ưu tiên cao nhất.
2. `docs/ai-agent/13_READ_ONLY_BOUNDARY_AND_MIGRATION.md` — ranh giới và checklist chuyển từ v1.0.
3. `docs/ai-agent/00_INDEX.md`.
4. `docs/ai-agent/01_PROJECT_CONTEXT_AND_SCOPE.md` → `12_DECISIONS_OPEN_QUESTIONS.md`.
5. `configs/tool_registry.yaml`, `configs/assistant_policy.yaml`, `configs/dialogue_ontology.yaml`.
6. `schemas/training_sample.schema.json`, `prompts/*`.

**Nguồn đối chiếu:** https://github.com/orgs/smartevent-ticketing (`smartevent-backend`, `smartevent-web`, `smartevent-infra`, `ai-service`). Không giả định AI Service đã được xây dựng. Không đưa bản tài liệu cũ lên trước bộ v1.2 trong thứ tự đọc của AI Agent.

**Dành cho lập trình viên:** Coding Agent có thể sửa code trên branch được giao; **AI Chatbot runtime** tuyệt đối không được thay đổi business data. Hai loại quyền này không đồng nhất.

## v1.2 security gates

Đọc tài liệu 14 → 15 → 16 → 17 trước khi lập trình. Không bật private hoặc child GET tools chưa đạt gate. `scripts/reference_readonly_executor.py` là harness unit test, KHÔNG phải runtime deploy. `python -m pytest -q tests` để kiểm tra contract.

Đọc thêm `configs/implementation_gates.yaml` (blockers), `configs/auth_delegation_contract.yaml`, `configs/rag_corpus_policy.yaml`, `schemas/rag_corpus_manifest.schema.json`.
