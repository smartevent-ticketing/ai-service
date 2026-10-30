# Triển khai khắc phục audit AI Service — 30/10/2026

Baseline: `c9776f48a991617f824abac1c9fb24bd3867bda9` trên `main`.
Đối chiếu báo cáo Principal QA (B01, M01–M08, D01–D05), kế hoạch 7 PR
“Khắc phục và hoàn thiện AI-Service” và kế hoạch chung
`Plan_Chatbot/CHATBOT_IMPLEMENTATION_PLAN_2026_10_30.md` trong workspace cha.

Trạng thái: đã triển khai các sửa đổi local bên dưới; **chưa nghiệm thu release**.
Đây là các nhóm thay đổi để review, không phải 7 PR đã được mở trên GitHub.

## 1. Điều chỉnh cách triển khai

Ưu tiên đóng lỗi tại boundary hiện có, giữ Clean Architecture và dùng lại parser,
gateway, retriever, DTO. Không mở gate để làm test chạy qua. Bằng chứng unit,
probe không mạng, HTTP test, model inference và E2E được phân biệt rõ.

| Nhóm kế hoạch | Đã triển khai trong đợt này | Điều kiện còn thiếu |
|---|---|---|
| PR-01 / AI-01,02 | Boundary EventCard; phân biệt contract/backend/timeout/tool-disabled; error envelope an toàn; request ID | Thực thi HTTP tests trên runner hỗ trợ asyncio |
| PR-02 / AI-03,04,05 | UTC `Z` giữ microsecond; validate criteria; CLEAR/REMOVE/SET; clock inject cho Ollama/PEFT; truyền đủ filter/topic vào prompt; alias không khớp chuỗi con; cô lập search mới sau FAQ | Browser Reset và inference model thật |
| PR-03 / AI-06,07 | Readiness công bố riêng khả năng search cơ bản và date/price bị chặn bởi PUBLISHED-CHILD; kiểm tra đầy đủ evidence thẻ giá | PostgreSQL, anonymous HTTP, projection và zero-write evidence |
| PR-04 / AI-08,09 | FAQ follow-up có điều kiện; không chuyển truy vấn tài khoản sang corpus; judge thiếu verdict/lỗi không phê duyệt evidence; giữ verifier extractive bảo thủ | HTTP knowledge stack, revocation/cold-start qua dịch vụ thật; semantic verifier độc lập |
| PR-05 / AI-10,11 | 30 search seed có exact expected tool args, status, reference clock; test nhãn độc lập với output NLU | 70 seed còn lại cần oracle chi tiết; held-out độc lập; model/embedding inference và benchmark thật |
| PR-06 / AI-12 | Health không lấy request NLU cuối làm bằng chứng model sẵn sàng; telemetry outcome/error code an toàn; manifest; wheel build | Full coverage gate, clean-wheel HTTP smoke, Docker và CI matrix từ xa |
| PR-07 | Ghi nhận các phụ thuộc và thứ tự nghiệm thu | E01–E10 toàn stack, rollback thực và phê duyệt gate |

## 2. Hợp đồng lỗi đã chốt cho AI

Các response lỗi chỉ chứa `code`, `message`, `request_id`, `retryable`.
`request_id` được server tạo, khớp header `x-request-id`; không phản chiếu message,
payload lỗi dependency, credential hoặc input validation của người dùng.

| Trường hợp | HTTP | Code / status |
|---|---|---|
| Thiếu scope/quantity cần làm rõ | 200 | ChatResult.status=CLARIFY |
| Tìm hợp lệ, không có kết quả | 200 | ChatResult.status=EMPTY |
| Tool chưa được duyệt | 200 | Fallback hội thoại, status=TOOL_DISABLED |
| Schema/projection sai từ gateway hoặc EventCard | 502 | UPSTREAM_CONTRACT_ERROR |
| Transport/backend không phục vụ, hoặc body bị transport từ chối | 503 | BACKEND_UNAVAILABLE |
| Deadline NLU hoặc business transport | 504 | UPSTREAM_TIMEOUT |
| Model không phục vụ, không có fallback | 503 | MODEL_UNAVAILABLE |
| Knowledge dependency lỗi | 503 | KNOWLEDGE_UNAVAILABLE |
| Request không hợp lệ/field lạ | 422 | INVALID_REQUEST |

Contract lỗi từ execute và lỗi projection đều đi qua cùng HTTP error handler.
Không gộp các lỗi dependency này vào TOOL_DISABLED. BFF phải giữ HTTP status và
ánh xạ các code công khai, không truyền nguyên nội dung lỗi nội bộ. `extra=forbid`
và field state mới optional/default được giữ.

EventCard kiểm tra UUID, name/city/venue, slug/route, timestamp có timezone,
thứ tự start/end, giá hữu hạn không âm, VND và toàn bộ price evidence với
`priceBasis=TICKET_FACE_VALUE` theo registry. Không suy luận tồn kho từ thẻ giá.

## 3. Chính sách state, model và RAG

- Mọi model delta được quy về CLEAR → REMOVE → SET; SET thắng REMOVE cho cùng
  slot dù thứ tự trong JSON khác nhau. Hai CLEAR hoặc hai alias operation mâu
  thuẫn bị từ chối. Sai kiểu falsy không được biến ngầm thành object/list rỗng.
- Xóa ngân sách vẫn xóa scope/operator; xóa ngày vẫn xóa cả cặp. Bộ lọc cũ được
  xóa khi chuyển từ FAQ sang một search mới; patch rõ ràng của lượt mới được giữ.
- Alias thành phố chỉ khớp nguyên tên ở parser model, ranh giới từ ở bộ luật.
  `duoi` và `dưới` cùng dùng LT. Chuẩn hóa UTC không làm mất phần lẻ giây.
- Rule fallback và prompt của mỗi adapter dùng cùng clock injectable. Ngày,
  operator và FAQ topic được chuyển đầy đủ vào context. Warning lỗi inference
  chỉ ghi loại exception, không ghi exception text từ provider.
- Chỉ nối FAQ topic khi có ngữ cảnh FAQ trước đó và câu hỏi tiếp bắt đầu bằng
  “còn/con”. Nhánh trạng thái thanh toán cá nhân giữ routing riêng.
- Nếu evidence judge lỗi hoặc thiếu verdict, chunk đó không được phê duyệt.
  Không thay verifier extractive bằng kiểm tra substring; không tuyên bố đã có
  entailment checker hay chất lượng model/RAG được nghiệm thu.
- `last_nlu_mode` chỉ là chẩn đoán. Model configured được báo `unverified` cho
  đến khi có kiểm tra provider độc lập; request thành công không mở readiness.

## 4. Kiểm chứng local

Môi trường: Windows, Python 3.12.10, dependency có sẵn trong `.venv`.

| Kiểm tra | Kết quả |
|---|---|
| Nhóm regression/offline được chọn | **310 PASS**, 14 HTTP cases deselected vì giới hạn event loop |
| Ruff lint và formatting | PASS; có chuẩn hóa định dạng file test budget cũ để qua gate toàn repo |
| Mypy | PASS, 58 source files |
| Compileall | PASS |
| Dependency locks/hash exports | PASS |
| Clean Architecture / READ_ONLY static guard | PASS |
| Runtime config source/package và knowledge schema | PASS |
| Immutable contexts | PASS, 49 files |
| Wheel build local không tải dependency | PASS |
| Full pytest/coverage >=90%, clean-wheel HTTP smoke | BLOCKED/NOT VERIFIED trong môi trường này |
| Docker, PostgreSQL, model thật và E2E | NOT VERIFIED |

JUnit của lượt chạy offline nằm ở `artifacts/audit-remediation-offline.xml`.
Manifest được tái tạo bằng script chuẩn sau sửa đổi; kiểm tra `--verify` trước bàn giao.

Các nhóm kiểm thử offline đã chạy: orchestration/projection/criteria/gates,
30 search seed có nhãn cụ thể, Rule/Ollama/PEFT với provider giả lập,
domain/settings/split, knowledge chunking/contracts/ingestion/retrieval,
evidence verdicts và evaluation analysis. Không dùng chúng làm live approval.

Đã xác định giới hạn môi trường bằng stack dump: TestClient/pytest-asyncio treo
trong `socket._fallback_socketpair → asyncio.proactor_events._make_self_pipe`,
trước khi dispatch request. Đã dừng các tiến trình test bị treo. Các probe
`test_audit_orchestration.py` thay scheduling bằng inline để kiểm tra coroutine
và error handler thật, không giả lập chúng thành HTTP test đã chạy đạt.

Pytest cần `--basetemp` mới bên trong `artifacts/` vì thư mục temp mặc định không
ghi được trong sandbox. Build wheel dùng thư mục TEMP/TMP trong workspace.
Docker API từ chối truy cập named pipe; chưa chạy Docker/PostgreSQL/model thật.

Lệnh full gate dành cho runner có hỗ trợ event loop/network:

```powershell
python -m compileall -q src scripts tests
python scripts/verify/verify_dependency_locks.py
python scripts/verify/static_verify.py
python scripts/verify/verify_runtime_config_sync.py
python scripts/knowledge/export_knowledge_schemas.py --verify
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest -q --cov=smartevent_ai --cov-report=term-missing --cov-fail-under=90
python scripts/verify/verify_contexts.py
python scripts/verify/source_manifest.py --verify
python -m pip wheel --no-deps --no-build-isolation . -w dist
python scripts/release/wheel_smoke.py dist
```

## 5. Công việc phụ thuộc chưa đóng

1. Infra B01: sửa FK `knowledge_active.index_id → knowledge_releases.index_id`,
   migration dữ liệu cũ, DB sạch/ingest/read/restart và quyền SELECT của reader.
2. Infra M01: chốt dense bắt buộc (503) hoặc degraded BM25 tường minh; nếu chọn
   degraded phải công bố effective mode. Không bỏ evaluation guard.
3. Backend: PostgreSQL `postgresTest`, Spring date/offset binding, query count,
   AVAILABLE seats, price evidence ở cả search không filter và counter lifecycle.
4. Web: AbortError khác TimeoutError, PUBLIC_HELP whitelist, error envelope,
   mounted hook race và Playwright Reset → FAQ → Search/card navigation.
5. AI/model: oracle đầy đủ cho mọi lượt dataset, tập nghiệm thu độc lập chưa dùng
   chỉnh prompt, inference model thật, đo cold-start/latency/structured-output,
   so sánh BM25/dense/hybrid và verifier có đánh giá độc lập.
6. Tích hợp: backend/knowledge fixture cô lập, kiểm tra anonymous/public boundary,
   snapshot DB trước/sau, E01–E10 và thực hành rollback. Chỉ sau đó review profile
   tích hợp được duyệt; các gate mặc định vẫn đóng.

Mốc A–E và 10 bước kế hoạch chung chưa được đóng bởi đợt sửa local này.
