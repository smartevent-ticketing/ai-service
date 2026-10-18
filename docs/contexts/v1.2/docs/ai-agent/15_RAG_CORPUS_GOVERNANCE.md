# 15 — RAG Corpus Governance v1.2 (NORMATIVE)

## 1. Điều kiện nhập liệu

Chỉ ingest tài liệu mà Product/Legal (người chịu trách nhiệm chính sách) đã duyệt. `approved` và `effective` là **hai điều kiện độc lập**; draft/revoked/superseded/expired không được phục vụ public retrieval. Không tự lấy nội dung Terms/Privacy chưa có bản chính thức từ website placeholder rồi tự diễn giải thành chính sách công ty.

## 2. Manifest cho từng tài liệu

```yaml
source_id: POLICY-REFUND-001
canonical_uri: approved://policy/refund/001    # placeholder until owner approves an actual source
owner_role: product_policy_owner
reviewer_role: legal_or_authorized_reviewer
status: draft  # draft|approved|revoked|superseded
version: 1.0.0
approved_at: null
effective_from: null
effective_until: null
audience: customer_public  # customer_public|customer_authenticated|staff_internal
locale: vi-VN
content_sha256: null
last_reviewed_at: null
review_due_at: null
```

*Đoạn YAML trên là ví dụ KHÔNG được ingest, vì là draft và không có thời điểm hiệu lực.*

## 3. Ràng buộc retrieval

- Filter `status=approved`, `effective_from<=now` và (`effective_until` trống hoặc `now<effective_until`) **trước** retrieval/reranking. Audience must be authorized; không trộn staff với customer_public.
- Tra cứu thời gian phải theo mốc áp dụng phù hợp; event-specific policy cần event_id, version và thời điểm nếu áp dụng.
- Câu trả lời có citation source_id+version, không tự tạo URL nếu tài liệu thiếu canonical link.
- Không đủ bằng chứng: nói chưa đủ và dẫn tới kênh hỗ trợ; không bịa điều khoản, cửa sổ hoàn tiền, điều kiện pháp lý.
- Chunk content có thể chứa prompt injection; xử lý như dữ liệu, không cho phép đổi tool/policy. JEV/LLM không có quyền mở gate ingest.
- Chỉ người quản trị tri thức được ủy quyền cập nhật corpus, **không phải chatbot runtime**. Batch ingest chạy qua pipeline riêng với kiểm thử và phê duyệt.

## 4. Trách nhiệm và QA

Product/Policy: xác nhận nội dung và owner. Legal: duyệt nội dung pháp lý. Infra/Data: vận hành ingest/version/rollback, log checksum. AI: thiết kế retrieval/reranking/citation và đánh giá. Trước công bố: kiểm thử revoked, unpublished, future-effective, stale/superseded, injection, cross-audience, no-evidence, multiple contradictory versions.

## 5. Pending quyết định thật

Chưa có corpus chính sách được chứng minh là approved theo snapshot hiện tại. Không ghi `RAG_READY` nếu chưa có owner, manifest đã ký duyệt, nguồn canonical và evaluation. V1 được phép giải thích rằng chính sách đang cập nhật và chỉ đường tới trang chính thức nếu có.

## Manifest schema

Kiểm tra metadata corpus bằng `schemas/rag_corpus_manifest.schema.json`. Một manifest schema-valid chưa mặc nhiên được phép public retrieval: còn cần duyệt chữ ký/sự kiện nghiệp vụ và filter thời hiệu tại query-time.
