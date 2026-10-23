# Vận hành pipeline tri thức 0.2.0

## Thử pipeline offline

Từ source checkout đã cài `requirements/dev.lock` và editable package:

```bash
python scripts/knowledge_smoke.py --output artifacts/knowledge-demo
```

Đầu ra gồm catalog TEST_ONLY, `build/release.json`, `chunks.jsonl`,
`BUILD_MANIFEST.json`, `evaluation.json` và thư mục publication có `CURRENT.json`.
Đích phải mới; công cụ không ghi đè kết quả cũ. Dữ liệu demo không cấp quyền bật runtime.

## Chuẩn bị nguồn thật

1. Review nội dung trong `datasets/knowledge_drafts/` cùng chủ chính sách. Không
   ingest `manifest.draft.json`; các trường phê duyệt/thời hiệu đang để trống.
2. Tạo catalog theo `configs/schemas/rag_catalog.schema.json`. Mỗi source có đường
   dẫn tương đối dưới corpus root, checksum byte gốc, title, canonical URI, version,
   owner/reviewer, hồ sơ approval, audience và thời hiệu có timezone.
3. Catalog production chỉ chứa nguồn public đã duyệt, còn hiệu lực. Ghi hồ sơ review
   ở nơi được quản trị; pin checksum catalog sau khi đối chiếu phê duyệt. Cờ approved
   và một chuỗi approval ID tự khai không phải bằng chứng pháp lý hay chữ ký số.
4. Xác định tokenizer/model profile và checksum từ asset đã được review. Không
   để model weights, corpus thật, catalog có thông tin nội bộ hoặc index vào Git.

## Build

CLI không tự tải tokenizer/model và không suy ra phê duyệt từ nội dung:

```bash
python -m smartevent_ai.tooling.offline_jobs.build_index --help
```

Các tham số bắt buộc gồm `--corpus-root`, `--catalog`, `--catalog-sha256`,
`--tokenizer`, `--tokenizer-sha256`, `--tokenizer-model`, `--tokenizer-revision`,
`--context-window`, `--source-revision` và `--output`. Dùng commit/revision và hash
thật; không dùng `main`/`latest`. Profile embedding E5 cần document prefix
`--prefix "passage: "`; query prefix của adapter E5 là `query: `.

Profile khởi điểm là 384 token/64 overlap. Ngân sách bao gồm context heading,
prefix và special tokens. Chunk có nguồn/vị trí chuẩn hóa; table row quá lớn
bị từ chối thay vì cắt âm thầm. Giới hạn loader Markdown/TXT là 1 MB mỗi tệp.

## Đánh giá

```bash
python -m smartevent_ai.tooling.offline_jobs.evaluate --help
python -m smartevent_ai.tooling.offline_jobs.benchmark_semantic --help
```

Evaluation nhận catalog/release cùng checksum, tập câu hỏi JSONL theo schema riêng,
`--at` có timezone và `--output` mới. Query có `case_id`, `group`, `split`, `query`,
`expected_sources` dạng `SOURCE-ID@version`; câu hỏi phải từ chối dùng danh sách rỗng.
Không để cùng nhóm paraphrase vào dev và test. Snapshot corpus vẫn chứa tài liệu
đích được phép truy xuất; đây không phải split mẫu huấn luyện ontology.

Benchmark semantic cần optional dependencies trong `requirements/rag.lock`, model
ONNX CPU, tokenizer cùng revision/hash và dimension thật. Phải build lại chunk
theo đúng tokenizer/profile đó trước khi đo. Báo cáo so sánh BM25/dense/hybrid,
source hit@1, recall@5, thời gian build/vector payload và latency theo query.
Vector payload bytes không phải toàn bộ RAM của process/model. Tập smoke chỉ có
hai tài liệu public, do đó recall@5 không đủ để chọn model hoặc đánh giá chất lượng
production; dense chưa có ngưỡng abstention đã hiệu chuẩn.

Không tải model trong CI mặc định. Kiểm thử ONNX dùng graph tổng hợp tự tạo;
benchmark model đa ngôn ngữ thật là bằng chứng riêng được lưu dưới `evidence/`.

## Hiệu chuẩn offline (không bao giờ bật tool)

```bash
python -m smartevent_ai.tooling.offline_jobs.analyze_evaluation --input artifacts/evaluation.json
```

`evaluate.py` ghi `records` từng case (case_id/split/query/expected/retrieved/
abstained/latency_ms/timed_out) kèm `timeouts_ms` cho case vượt 2000 ms.
`analyze_evaluation` đọc records và in báo cáo hiệu chuẩn (Brier/ECE theo
abstention-as-confidence: abstained 0.1, answered 0.9; latency p50/p95) với
nhãn `OFFLINE_ONLY`. Input hỏng (thiếu field, trùng case, group leak
dev/test) cho `evaluation_ready=false`, không in metric nửa vời. Ngưỡng hiệu
chuẩn chỉ phục vụ tuning offline; không có code path nào đọc báo cáo để bật
tool (`SPEC_TEST_ONLY`/`BLOCKED`/`NOT_RUN` không phải `PASS`).

## Verdicts bằng chứng (kept/conflicts/dropped)

`domain/evidence.py` (stdlib-only) phân loại mỗi chunk sau BM25-rank, theo đúng
thứ tự: injection → premise-contradiction → relevance (< 0.5 query-term
coverage) → evidence. `CONFLICTS` được giữ làm undercutting evidence có
citation (đánh dấu `[BẰNG CHỨNG PHẢN BIỆN — cần đối chiếu]`), không lọc âm
thầm; check crash/timeout → `DROPPED`. Judge fail toàn bộ → fallback BM25
thuần, không fail-closed request.

## Publish và rollback

```bash
python -m smartevent_ai.tooling.offline_jobs.publish artifacts/knowledge-demo/build artifacts/published
```

Publisher kiểm checksum rồi tạo thư mục bất biến theo release hash và thay
`CURRENT.json` nguyên tử. Publish lại cùng release là idempotent; publish bản build
cũ có thể thay pointer để rollback. **Runtime không tự tin pointer này** và không
tự bật gate: operator phải review config/trust anchors và giữ catalog nguồn/thu hồi
hiện hành. Không rollback catalog để phục hồi quyền của nguồn đã revoked/expired.

## Bật runtime sau nghiệm thu

- Mount catalog/release và cấu hình dưới quyền chỉ đọc của process API; chỉ pipeline
  quản trị có quyền ghi. Pin `catalog_sha256` và `release_sha256` trong `rag.yaml`.
- Chốt bằng chứng cho `RAG-APPROVED-CORPUS` và `RAG-READONLY`; unit/TEST_ONLY smoke
  không đủ để đổi thành PASS. Cấu hình mẫu và gate trong repository vẫn tắt/blocked.
- Cập nhật cả bộ config nguyên tử. Khi đổi catalog/release, cập nhật checksum sau
  review; runtime kiểm lại chúng mỗi lần đọc và không giữ cache quyền cũ.
- Không có environment toggle bật riêng RAG/tool. `CONFIG_DIR` chỉ chọn bộ cấu hình
  được quản trị, không thay thế việc duyệt gate và corpus.
- Quan sát `/health/ready`: `policy_retrieval.status` là disabled/ready/unavailable;
  `business_tools_enabled` và trạng thái business vẫn độc lập. Không gộp RAG-ready
  thành chứng nhận production-ready cho toàn hệ thống.

## Khi từ chối nguồn

Hash sai, catalog stale/future/expired, gate bị đóng, nguồn bị thu hồi/khác audience,
version mâu thuẫn hoặc không tìm được bằng chứng đều dẫn tới fallback không citation.
Trích đoạn đầu tiên quá dài cũng không bị cắt để tạo câu trả lời thiếu ngoại lệ.
Không để client chọn audience, catalog, path, model hay quyền truy cập qua body chat.

Schema/profile mới phải qua `export_knowledge_schemas.py --verify`, config sync,
negative tests, source manifest, wheel smoke và CI. Không sửa ngữ cảnh v1.2 gốc.
