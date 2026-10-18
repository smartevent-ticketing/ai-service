# 00 - Bản đồ tài liệu AI Agent

## Mục tiêu

**QUYẾT ĐỊNH MỚI v1.2:** Chatbot chỉ READ/ANALYZE/RECOMMEND, không được tạo/sửa/xóa dữ liệu nghiệp vụ. Xem `13_READ_ONLY_BOUNDARY_AND_MIGRATION.md`.

Bộ tài liệu này biến ngữ cảnh hội thoại thiết kế thành một đặc tả có thể kiểm tra, để AI Agent không phải suy luận lại kiến trúc từ đầu.

## Bản đồ nhanh

| Tài liệu | Trả lời câu hỏi |
|---|---|
| 01 Project Context | Dự án đang giải quyết bài toán gì? Phạm vi V1/V2? |
| 02 Current Architecture | SmartEvent hiện có gì? Module, stack, API, source of truth? |
| 03 Target AI Architecture | AI Service phải được xây như thế nào? |
| 04 Business Flows | Luồng nghiệp vụ và state machine nào phải giữ đúng? |
| 05 Dialogue Ontology | Chatbot hiểu intent/slot/state/action như thế nào? |
| 06 Data/Fine-tuning/RAG/JEV | Dữ liệu huấn luyện và retrieval được tổ chức ra sao? |
| 07 Tool/API Contracts | Model được gọi những tool nào và map vào API nào? |
| 08 Security Rulebook | Những luật nào là bất biến an toàn? |
| 09 Implementation Plan | Làm theo thứ tự nào trong 8 tuần? |
| 10 Test/Evaluation | Đo chất lượng và nghiệm thu thế nào? |
| 11 Agent Protocol | AI coding/audit agent phải làm việc ra sao? |
| 12 Decisions/Open Questions | Những gì đã chốt và những gì chưa chốt? |
| 13 Read-Only Boundary | Quyền đọc tuyệt đối, cấm gọi mutation và cách sửa từ v1.0. |

## Từ vựng chuẩn

- **Trợ lý hội thoại hướng tác vụ (Task-Oriented Dialogue System - TODS):** hệ thống theo dõi trạng thái và giúp người dùng hoàn thành mục tiêu nhiều bước.
- **Mô hình ngôn ngữ nhỏ (Small Language Model - SLM):** mô hình 1-2B tham số được dùng cho tác vụ hẹp, có cấu trúc.
- **Tinh chỉnh hạng thấp (Low-Rank Adaptation - LoRA/QLoRA):** kỹ thuật chỉ huấn luyện adapter thay vì toàn bộ trọng số.
- **Truy xuất tăng cường (Retrieval-Augmented Generation - RAG):** tìm tài liệu có căn cứ trước khi tạo câu trả lời.
- **Bộ đánh giá JEV:** thành phần quyết định có cấu trúc, tùy chọn, dùng cho routing/evidence scoring.
- **Bộ tối ưu vé (Ticket Optimizer):** code xác định trước để lọc hard constraints và xếp hạng soft constraints.
- **Công cụ nghiệp vụ (Business Tool):** adapter cho API backend được allowlist.
- **Thay đổi trạng thái (State Delta):** phần thay đổi của dialogue state ở lượt hiện tại, thay vì model sinh lại toàn bộ state.

## Cập nhật v1.2 — đọc ngay sau AGENTS

- [14 Tool Runtime Contract](14_TOOL_RUNTIME_CONTRACT_AND_SECURITY_GATES.md): typed inputs/outputs, raw QR filtering, customer-self-only, published-only, gates.
- [15 RAG Corpus Governance](15_RAG_CORPUS_GOVERNANCE.md): chỉ ingest chính sách approved và có hiệu lực.
- [16 Evaluation & Reproducibility](16_REPRODUCIBILITY_EVALUATION_MANIFEST.md): model/dataset/repo SHA, baseline/test.
- Các private tools và 5 child-event tools được giữ **disabled** đến khi gate đạt; không gọi chúng là năng lực đã triển khai trong V1.
