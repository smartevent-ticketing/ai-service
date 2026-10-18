# 06 - Dữ liệu, fine-tuning, RAG và JEV

**Ranh giới v1.2:** Mô hình fine-tune chỉ sinh intent/slots/state_delta nội bộ và hành động chỉ đọc. Mẫu dạy gọi POST/PUT/PATCH/DELETE, tạo giữ chỗ hoặc gửi refund-review là **dữ liệu huấn luyện sai**; phải đổi nhãn thành giải thích giới hạn/điều hướng UI. Không dùng giá/tồn kho/order thật làm tri thức thuộc trọng số.

## 1. Fine-tuning strategy

Mô hình khởi đầu: **Qwen3-1.7B** hoặc lớp 1.5B tương đương để đối chứng. Phương pháp: **Supervised Fine-Tuning bằng QLoRA/LoRA**.

Không fine-tune để model ghi nhớ catalog/tồn kho/chính sách. Fine-tune để model giỏi hơn ở:

- intent classification;
- entity/slot extraction;
- state delta;
- proposed action/tool intent;
- ambiguity/correction/negation trong tiếng Việt.

## 2. Quy mô dataset V1

- Train: khoảng 4.000 mẫu.
- Validation: 600 mẫu.
- Test: 600 mẫu.
- Tổng: khoảng 5.200 mẫu.

Đây là kế hoạch khởi đầu; chất lượng được quyết định bằng learning curve và error analysis, không bằng số mẫu tuyệt đối.

## 3. Phân bổ train đề xuất

| Nhóm | Mục tiêu |
|---|---:|
| Intent + slot | ~1.200 |
| Dialogue state update | ~1.200 |
| Action/tool selection | ~600 |
| Correction/negation/ambiguity/reference | ~600 |
| Safety/error/out-of-scope | ~400 |

Có thể multi-label/multi-task trên cùng mẫu.

## 4. Nguồn dữ liệu

1. Hand-written seed scenarios từ nghiệp vụ thực.
2. Synthetic dialogues được tạo từ ontology/API contracts.
3. Paraphrase tiếng Việt theo vùng cách nói khác nhau.
4. Adversarial/edge cases.
5. Hội thoại thực tế sau này chỉ dùng khi có quyền xử lý phù hợp, đã loại PII và review.

Synthetic sample không được mặc định là ground truth. Cần schema validation + business validation + review.

## 5. Tách train/val/test

Split theo `dialogue_group`/scenario family, không split ngẫu nhiên từng turn. Không để paraphrase gần giống của cùng scenario rơi vào train và test khác nhau.

## 6. Schema gốc

Mẫu gốc phải chứa:

- sample id/version/language;
- previous state;
- user message;
- expected intent/entities/state delta/proposed action;
- metadata source/difficulty/scenario/group;
- optional negative/safety labels.

Xem `schemas/training_sample.schema.json`.

## 7. RAG corpus

Chỉ index tài liệu người dùng được phép thấy:

- FAQ;
- hướng dẫn mua vé;
- hướng dẫn payment;
- chính sách refund/support;
- ticket transfer/help;
- check-in guide;
- điều khoản/chính sách đã duyệt.

Không index secrets, runbook security, admin-only nội dung vào public retrieval namespace.

### Metadata bắt buộc

- source ID;
- title;
- canonical URL/path;
- version;
- effective dates;
- audience/access level;
- document type;
- checksum/content hash.

## 8. Retrieval strategy

V1 ưu tiên hybrid retrieval:

- keyword/BM25/full-text;
- semantic vector retrieval nếu benchmark cho thấy cần;
- metadata filter;
- rerank/evidence evaluation.

Không bắt buộc vector DB độc lập ngay từ đầu. Có thể dùng PostgreSQL + extension phù hợp hoặc service riêng sau benchmark.

## 9. JEV

JEV là optional DecisionEvaluator.

Thử nghiệm tại hai vị trí:

1. Router/evaluation signal cho intent category.
2. RAG evidence relevance/answerability/conflict signal.

Phải benchmark với baseline không JEV theo accuracy, calibration, latency và cost. Nếu không cải thiện đủ, tắt JEV mà không ảnh hưởng core flow.

## 10. Những dữ liệu không được fine-tune

- access/refresh token;
- password/API secret;
- QR credential thật;
- payment params nhạy cảm;
- user PII không có cơ sở sử dụng;
- inventory snapshot thật mang tính thời điểm;
- giá/sale phase hiện hành;
- internal admin data.

## 11. Experiment matrix

- A: base SLM + prompt.
- B: base SLM + optimized prompt/schema.
- C: SLM + QLoRA.
- D: C + TODS + Tools.
- E: D + RAG.
- F: E + JEV evaluator.

Mỗi bước phải chứng minh contribution độc lập, tránh kết luận sai vì thay nhiều biến cùng lúc.

## v1.2 — Dataset và RAG hardening

Train JSONL phải đáp ứng schema `dataset_contract=1.2`; field `previous_state` là flat map. `state_delta` dùng `oneOf` typed operations, mọi slot ngoài ontology bị từ chối; `secondary_intents` phải thuộc enum; sample thiếu `scenario_family` bị từ chối. Xem tài liệu 16 về chia dữ liệu theo nhóm và bằng chứng benchmark.

RAG chỉ ingest manifest approved+effective. Chưa có source corpus verified nên **không được coi RAG policy answers đã nghiệm thu**. Xem tài liệu 15. JEV remains optional, cần benchmark với fallback, tuyệt đối không nhận raw private payload.
