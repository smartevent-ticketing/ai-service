# 09 - Kế hoạch triển khai và backlog

## 1. Chiến lược tổng thể

Triển khai theo vertical slice có thể demo, không xây toàn bộ framework trước rồi mới tích hợp.

## 2. Kế hoạch 8 tuần

### Tuần 1 - Foundation và contract

- Khởi tạo FastAPI/pyproject/Dockerfile.
- Chốt ontology, state schema, **GET-only tool registry**, assistant policy READ_ONLY.
- Xác định chat API contract.
- Thiết lập lint/type/test/CI cơ bản.
- Chốt auth propagation design.

**Gate:** `/health` + `/chat` skeleton, schema tests, docs versioned.

### Tuần 2 - TODS / Dialogue Engine

- DialogueState model.
- StateDelta validator/merger.
- Policy Engine.
- State machine.
- Persistence abstraction.
- Tests correction/negation/reference/switch-task.

**Gate:** transition tests pass, deterministic merge.

### Tuần 3 - Backend Tools + frontend chat shell

- Backend client + typed adapters **chỉ GET**; deny-by-default executor chặn method khác.
- Public event/ticket/inventory/seat tools.
- Private auth-aware **GET** tools cơ bản; kiểm tra ownership và visibility event chưa công bố.
- Next.js chat feature + BFF route + SSE nếu dùng.

**Gate:** chat -> backend real GET event data end-to-end; không có business writes; mọi unpublished-event GET đã được bảo vệ.

### Tuần 4 - Dataset + baseline

- Seed 1.000 mẫu review.
- Dataset validation scripts.
- Split theo scenario group.
- Baseline Qwen3-1.7B/base competitor.
- Metrics dashboard/report.

**Gate:** baseline report có reproducible command.

### Tuần 5 - QLoRA

- Mở rộng ~4.000 train + 600 val + 600 test.
- Train adapter.
- Compare base/prompt/QLoRA.
- Error analysis.
- Chỉ giữ adapter nếu cải thiện đủ.

**Gate:** model card nội bộ + eval report.

### Tuần 6 - Ticket Optimizer + RAG

- Hard/soft constraint model.
- Candidate generator/ranking/relaxation.
- RAG ingestion/retrieval/source metadata.
- Grounded response composer.

**Gate:** zero hard-constraint violation trên golden optimizer tests; policy QA có source.

### Tuần 7 - JEV, security, resilience

- DecisionEvaluator abstraction.
- JEV adapter + fallback.
- Prompt injection tests, **đặc biệt lệnh yêu cầu AI POST/PUT/PATCH/DELETE**.
- Rate limit/tool budget/circuit breaker.
- Auth/cross-account negative tests; kiểm thử business DB không bị chatbot ghi trong mọi E2E.

**Gate:** chatbot chạy khi JEV tắt/lỗi; không cross-account leak; không tool mutation trong registry và không side-effect từ GET.

### Tuần 8 - E2E, load, report

- E2E scenarios.
- Load test AI route và backend-sensitive flow.
- p50/p95/p99, cost/session, model/tool calls/session.
- Demo script + deployment docs.

**Gate:** quality gates đạt hoặc deviation được ghi rõ.

## 3. PR/branch decomposition

Khuyến nghị:

- `feat/ai-foundation`
- `feat/dialogue-ontology`
- `feat/dialogue-state`
- `feat/backend-tools`
- `feat/chat-bff`
- `feat/chat-ui`
- `feat/dataset-pipeline`
- `feat/qwen-qlora`
- `feat/ticket-optimizer`
- `feat/rag`
- `feat/jev-evaluator`
- `test/ai-evaluation`
- `test/ai-load`
- `docs/ai-architecture`

Không gộp tất cả thành một PR.

## 4. Dependency order

Ontology -> State/Policy -> Tools -> UI slice -> Dataset baseline -> Fine-tune -> Optimizer/RAG -> JEV -> Hardening.

Fine-tuning trước ontology/tool contract là sai thứ tự vì label sẽ thay đổi liên tục.

## 5. Backlog sau V1

**Chỉ mở rộng khả năng đọc, phân tích và điều hướng; không thêm quyền mutation:**

- **Không nằm trong roadmap:** create/update/cancel reservation/order/refund/ticket bằng AI. Kể cả bản V2/V3 chatbot vẫn READ_ONLY.
- Personal preference profile có consent.
- Learned ranking sau hard filters.
- Proactive notifications.
- Voice.
- Organizer copilot.
- Multi-language.

## v1.2 — Điều chỉnh thứ tự gate trong 8 tuần

**Giai đoạn nền tảng (tuần 1–2):** ưu tiên typed registry, safe projection, customer-only auth design, executable reference tests. **Tuần 3–4:** mở public/child GET dần sau published-only backend tests; nếu chưa xong chỉ demo search công khai, không tuyên bố recommendation toàn diện. **Tuần 4–5:** dataset contract 1.2 + SLM baseline/QLoRA theo kết quả validation. **Tuần 6:** RAG chỉ khi có policy owner approved và corpus version. **Tuần 7:** JEV chỉ benchmark tùy chọn, không blocking release. **Tuần 8:** E2E + security gates + performance run manifest; mọi gate thiếu phải ghi release blocker, không làm giả tính năng.

Tách PR theo trục `readonly-policy`, `projection`, `backend-visibility`, `auth-self-only`, `dataset`, `model`, `rag-governance`, `evaluation`. Không gộp tất cả thành một feature PR.
