# Bằng chứng kiểm chứng foundation RAG 0.2.0

Ngày: 18/10/2026. Phạm vi: pipeline tri thức chỉ đọc, corpus khởi tạo bản nháp,
chat trích đoạn và benchmark semantic offline. Không phải nghiệm thu production.

## Trạng thái tính năng

- Đã có hợp đồng nguồn/chunk/citation, ingest Markdown/TXT, token-budget chunking,
  BM25 có lọc quyền/thời hiệu, kiểm tra lại catalog và câu trả lời trích đoạn.
- CLI build/evaluate/publish hoạt động độc lập; serving không import tooling/writer.
- Đã chạy ONNX CPU đa ngôn ngữ thật ngoài unit tests. Semantic/hybrid chưa phục vụ chat.
- RAG mặc định disabled; cả RAG gates và các business gate chưa được tự chuyển PASS.
- Năm tài liệu FAQ/chính sách khởi tạo là DRAFT, không có hồ sơ phê duyệt giả định.

## Quality gates

Kiểm tra chạy từ bản xuất mã nguồn theo manifest, tách khỏi file local:

| Gate | Kết quả |
|---|---|
| Windows / Python 3.12.10 | 235 PASS, 1 SKIP; coverage 93,10% |
| Windows / Python 3.11.9 | 235 PASS, 1 SKIP; coverage 93,10% |
| Wheel build từ source export | PASS, setuptools 83.0.0 |
| Wheel cài vào venv mới, CWD trống | PASS, kể cả khi caller có PYTHONPATH trỏ source |
| Schema/config/lock integrity | PASS |
| Runtime / optional RAG / dev-build audit | Không có advisory đã biết sau nâng pin |
| Remote Linux/Windows CI và Docker | Theo run gắn với commit trên Actions; chưa dùng định nghĩa workflow làm bằng chứng PASS |

Smoke harness được gia cố để pip cũng chạy isolated tại CWD trống, bỏ ảnh hưởng
PYTHONPATH/PYTHONHOME và cấu hình ứng dụng local. Cách này ngăn pip nhầm metadata
của source checkout là wheel đã được cài. Package được kiểm tra import từ prefix
của venv mới, có YAML/schema fallback, RAG disabled và không import thư viện model.

Wheel đã kiểm tra: `smartevent_ai_service-0.2.0-py3-none-any.whl`, 75016 byte,
SHA-256 `40e835a156cc041416395b959eef4e6108941897cacfd07852abd713bbd8171a`.

Compile, static guard, Ruff/format, Mypy (46 source files), schema/config sync,
lock/export integrity và 47 historical reference tests đã PASS. 49 checksum
ngữ cảnh gốc được xác minh riêng. Starlette TestClient còn một deprecation warning;
không suppress warning. Symlink test bị SKIP trên host Windows do không có quyền
tạo symlink; đây không phải PASS của ca đó, Linux CI phải chạy kiểm tra tương ứng.

## Dependency audit

Audit runtime và optional RAG graph không có advisory đã biết tại thời điểm chạy.
Audit mở rộng dev/build phát hiện advisory ở ONNX 1.19.1, pytest 9.0.2 và
setuptools 82.0.1; các pin được nâng lần lượt thành 1.22.0, 9.0.3 và 83.0.0.
Sau nâng, dev graph audit không có advisory đã biết, không thêm ignore exemption.
Kết quả không bảo đảm sẽ không xuất hiện advisory mới trong tương lai.

## Bằng chứng retrieval

[Lexical smoke](evidence/rag_lexical_smoke.json) có 11 câu hỏi TEST_ONLY, chia
dev/test theo nhóm, bao gồm không có bằng chứng và canary nội bộ. Trên tập nhỏ
này BM25 đạt source recall@5 và negative-abstention rate 1,0. Không xem đây là
benchmark sản phẩm, corpus thật hoặc bằng chứng đã duyệt điều khoản.

[Semantic benchmark](evidence/rag_semantic_benchmark.json) chạy CPU với:

- Model: `Xenova/multilingual-e5-small`, revision
  `761b726dd34fb83930e26aab4e9ac3899aa1fa78`.
- ONNX SHA-256: `f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193`.
- Tokenizer SHA-256: `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`.
- 384 chiều, attention-mask mean pooling, L2, query/passage prefix; cùng tokenizer
  đã được pin để tạo chunk 384/64. Không tải asset trong startup/API/CI mặc định.
- Chỉ có hai tài liệu public đủ điều kiện, bốn vector. Recall@5 của BM25/dense/hybrid
  đều 1,0 nên không đủ sức phân biệt chất lượng. Source hit@1 dev: BM25 1,0,
  dense 2/3, hybrid 1,0; test cả ba 1,0. Không kết luận ưu thế từ mẫu nhỏ này.
- Thời gian theo query gồm embedding và các bước ranking/fusion, không gồm load model.
  Vector payload 6.144 byte không phải toàn bộ RAM; peak process RAM chưa đo.
- Dense abstention chưa được hiệu chuẩn; không chọn dense/hybrid cho runtime.

Benchmark giữ `runtime_enable_authorized=false`. Model asset/cache/build tạm được
loại khỏi Git; chỉ lưu báo cáo nhỏ và hash phục vụ đối chiếu/tái lập.

## Gates còn lại

Corpus canonical thật, người phê duyệt, evaluation đa dạng độc lập, cross-section
policy completeness, SLO/load/abuse controls, live business/auth/zero-write và
generation/model/JEV vẫn cần bằng chứng riêng. Không dùng fixture để nghiệm thu.
Trạng thái remote CI của commit mới theo [Actions](https://github.com/smartevent-ticketing/ai-service/actions/workflows/ci.yml).
