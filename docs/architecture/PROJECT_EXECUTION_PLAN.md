# Review mã nguồn và kế hoạch triển khai SmartEvent AI Service

Ngày: 23/10/2026. Trạng thái: KẾ HOẠCH ĐỀ XUẤT, chưa phải bằng chứng nghiệm thu.
Baseline: `861bfcd` trên `loop/p0-pr4-inplace-hardening`, cộng các sửa đổi chưa
commit của lần review trước. Kế hoạch không mở tool, thay quyền hoặc sửa repo khác.

Cập nhật thực hiện: REV-01 và cấu hình CI của OBS-02 đã được sửa trực tiếp trong
working tree. PR-00 còn chờ các gate kỹ thuật đầy đủ và CI remote; chi tiết bằng
chứng tại [REVIEW_LOG.md](REVIEW_LOG.md).

## 1. Kết luận và phạm vi

Giữ Clean Architecture hiện tại. Domain/application đã tách khỏi framework và
hạ tầng; chưa có lý do từ review này để viết lại dự án hoặc chuyển sang nhiều
microservice. Tách thêm use case theo luồng khi triển khai, không tạo skeleton
provider hoặc module chưa có nhu cầu.

Mục tiêu ưu tiên: hoàn thành một luồng chỉ đọc từ người dùng đến dữ liệu đã kiểm
chứng: tìm sự kiện → xem kết quả → chọn sự kiện → xem chi tiết → hỏi chính sách →
điều hướng người dùng tự thao tác. Đề xuất vé dựa trên snapshot và đọc tài khoản
là các mốc tiếp theo, có gate riêng. Model sinh văn bản/QLoRA/JEV là hướng đánh giá
sau baseline; không trở thành điều kiện chặn hoàn thành luồng công khai.

Không có giai đoạn tự giữ chỗ, tạo đơn, thanh toán, hủy, chuyển vé hay hoàn tiền.
`POST /api/v1/chat` không cấp quyền ghi nghiệp vụ.

## 2. Phát hiện từ review hiện tại

### REV-01 — P2: số lượng vé lọt vào từ khóa tìm kiếm

Vị trí: `src/smartevent_ai/adapters/outbound/rule_nlu.py`, `_extract_search_query`,
Bộ luật trước bản sửa chỉ bỏ cụm số lượng ở đầu và đòi khoảng trắng sau đơn vị.
Tái hiện trước khi sửa qua NLU → merge_state → EventSearchCriteria:

| Câu hỏi | quantity | q trước khi sửa | q sau khi sửa |
|---|---:|---|---|
| Tìm 2 vé ở Hà Nội | 2 | `2 vé` | không gửi q |
| Tìm 2 ghế ở Đà Nẵng | 2 | `2 ghế` | không gửi q |
| Tìm concert 3 vé dưới 800 nghìn tổng | 3 | `concert 3 vé` | `concert` |
| Tìm 3 vé concert ở Hà Nội | 3 | `concert` | `concert` |
| Tìm concert 2026 ở Hà Nội | chưa có | `concert 2026` | giữ `concert 2026` |

Ảnh hưởng: khi search được nghiệm thu và mở, bộ lọc text có thể loại mất sự kiện
phù hợp. Hiện tool vẫn disabled; review này không tuyên bố đã gây truy vấn live
hoặc leak dữ liệu. Đã sửa local trong PR-00: dùng cùng bộ nhận diện quantity để
loại cụm số lượng ở mọi vị trí trong q và chuẩn hóa khoảng trắng. Các số không
kèm đơn vị vé/ghế vẫn thuộc tên sự kiện. Test bao phủ state, arguments cuối và
luồng chat làm rõ ngân sách; chưa suy ra search live đã được nghiệm thu.

### OBS-02 — CI cần đường chạy phù hợp với nhánh hiện tại

`.github/workflows/ci.yml` trước bản sửa chỉ nhận push vào main/dev/codex/**/feat/**/fix/**;
nhánh `loop/p0-pr4-inplace-hardening` không khớp. Đã bổ sung `loop/**` và test kiểm
tra nhánh hiện tại khớp trigger. Giữ permission `contents: read`, PR vào main/dev
và workflow_dispatch. Cấu hình mới chưa được push hoặc chạy remote; trước nghiệm
thu phải có run gắn với đúng head.

### Những phần thiếu có chủ đích, chưa phải lỗi mới của bản vá

| Phần | Bằng chứng mã nguồn | Việc chưa hoàn thành |
|---|---|---|
| Tìm sự kiện | `application/chat.py`, `_search_events`; `response_composer.py`, `search_result` | Chỉ soạn số lượng kết quả; chưa trả danh sách sự kiện/cards và metadata cho UI |
| Xem chi tiết | `domain/dialogue.py` có EVENT_DETAIL; chat chưa có handler tương ứng | Chưa có chọn ứng viên, revalidation và use case chi tiết |
| Phân trang | `domain/search.py`, `from_state` luôn tạo trang 0 | Chưa có chuyển trang/xem thêm; composer còn phải xét has_previous/result_complete khi mở luồng này |
| Nghiệp vụ live | Registry có 14 tool, tất cả disabled; chỉ search_events có caller | Thiếu bằng chứng backend/public visibility/zero-write và các use case còn lại |
| Tư vấn vé | `domain/recommendation.py` ghi EXPLICIT_DEAD | Chưa kiểm tra freshness/quota/seat và chưa được gọi từ chat |
| Tri thức | Ingest/chunk/BM25/citation có implementation, rag.yaml disabled | Thiếu corpus thật được duyệt và evaluation độc lập; chat hiện chỉ nối REFUND_POLICY |
| Dữ liệu riêng tư | Gateway từ chối authenticated tools | Thiếu cơ chế BFF delegation và chứng minh CUSTOMER_SELF_ONLY |
| Vận hành | HTTP có DTO và request telemetry | Chưa có bằng chứng body/admission/rate limit, load/SLO và triển khai hoàn chỉnh |

Sáu lỗi của lần review trước đã có sửa đổi và hồi quy. Evidence judge hiện chỉ
nhận diện mẫu khẳng định phổ quát hoàn tiền rõ ràng; không phải bộ suy luận ngữ
nghĩa tổng quát. Brier/ECE dùng fixed_decision_proxy, không chứng minh model đã
được hiệu chuẩn.

## 3. Nguồn bằng chứng và giới hạn kiểm chứng

- Lần sửa trước: 189 test không cần HTTP/async và 47 test tham chiếu lịch sử PASS;
  wheel build PASS. Full suite/coverage bị BLOCKED_ENV tại socketpair của event
  loop Windows. Không coi subset hoặc smoke coroutine là full-suite PASS.
- Sau sửa REV-01/OBS-02: full suite 348 test PASS, coverage 92,47% trên Windows /
  Python 3.12.10 với `COVERAGE_CORE=pytrace`; bộ đo mặc định gặp native access
  violation. Không thay event loop hoặc skip test. 47 test lịch sử PASS; compile,
  static/config/schema/lock, Ruff/format, Mypy, pip check và wheel build PASS.
  Knowledge smoke TEST_ONLY PASS. Chưa có CI remote, advisory mới, clean-wheel
  smoke hoặc Docker smoke cho bản vá hiện tại; xem REVIEW_LOG.md.
- Tập training mẫu có 12 record, 4 dialogue group. RAG fixture có 15 câu hỏi
  (7 dev, 8 test). Đây là fixture, không phải bằng chứng chất lượng sản phẩm/model.
- Đã đọc controller và PageResponse của bản backend local bên cạnh chỉ để đối
  chiếu sơ bộ endpoint/params. Git metadata của repo đó không truy cập được; chưa
  pin được SHA hoặc xác minh bản này trùng deployment/remote. Không nâng trạng
  thái gate từ việc đọc controller.
- Controller search local nhận q/city/categoryId/Pageable; chưa có tham số date
  range. PR-01 phải xác minh lại hợp đồng thực tế, không tự thêm filter chưa có.
- Không sửa backend/BFF/infra. Công việc thuộc các repo đó cần owner thực hiện
  trong thay đổi riêng. Bằng chứng live integration/advisory/clean-wheel/Docker
  cho head hiện tại còn phải được hoàn tất trên môi trường đủ quyền.

## 4. Kiến trúc triển khai

1. Domain: giá trị nghiệp vụ, state, điều kiện đủ của snapshot, money/quantity và
   quy tắc xếp hạng; chỉ standard library.
2. Application: use case SearchEvents/GetEventDetails/RecommendTickets/ReadAccount
   khi thật sự triển khai; định nghĩa port và kết quả typed bằng dataclass.
3. Adapters: ánh xạ HTTP/Pydantic, NLU, backend response, policy retrieval. Không
   truyền raw backend JSON sang model hoặc response của chat.
4. Infrastructure: settings, wiring, client lifecycle, trusted config và giới
   hạn tài nguyên. Config chuẩn ở configs, resource fallback đồng bộ byte.
5. Offline tooling: build/publish/evaluate/train chạy riêng. HTTP không có upload,
   crawler, writer hoặc đường import offline jobs.

BFF sở hữu phiên người dùng, xác thực và lifecycle/retention của hội thoại khi
cần lưu. AI Service tiếp tục stateless ở MVP; conversation_id/previous_state chỉ
là ngữ cảnh, không phải quyền truy cập. Candidate selection là input chưa tin
cậy, phải resolve từ danh sách do hệ thống cấp và GET lại dữ liệu hợp lệ. Không
thêm database hội thoại vào AI Service trong kế hoạch này.

## 5. Backlog triển khai theo PR

Ngày công dưới đây chỉ là ước lượng kỹ thuật cho AI Service, giả định có người
phối hợp backend/BFF/QA. Không bao gồm chờ quyền truy cập, duyệt corpus, gán nhãn
hay sửa backend. Chưa gắn lịch cam kết khi chưa có owner và ngày bàn giao phụ thuộc.

| PR | Kết quả | Phụ thuộc | Ngày công dự kiến |
|---|---|---|---:|
| PR-00 | Khóa baseline, sửa REV-01, hoàn tất gate kỹ thuật | Working tree hiện tại | 1–2 |
| PR-01 | Hợp đồng hành trình, HTTP/UI và backend có version | PR-00, owner backend/BFF | 1–2 |
| PR-02 | Tích hợp GET search/detail đã kiểm chứng | PR-01, backend test và trace/snapshot | 3–5 |
| PR-03 | Kết quả có cấu trúc, chọn sự kiện, xem thêm và state | PR-01; tích hợp cuối với PR-02 | 3–5 |
| PR-04 | Chính sách/FAQ có nguồn và corpus thật | PR-01, policy owner và bộ câu hỏi | 3–5 |
| PR-05 | Đọc areas/types/phases/inventory/seats đủ điều kiện | PR-02, backend child visibility | 3–5 |
| PR-06 | Đề xuất vé có kiểm tra snapshot và hard constraints | PR-03, PR-05 | 3–5 |
| PR-07 | Tích hợp chat BFF/UI theo hợp đồng | PR-01; nghiệm thu cùng PR-03/04 | 2–4 |
| PR-08 | Admission/rate/resource controls, load và release evidence | PR-03/04/07; PR-06 nếu scope có tư vấn vé | 3–5 |
| PR-09 | Đọc dữ liệu tài khoản CUSTOMER_SELF_ONLY | PR-01/07, verified auth và backend ownership | 4–7 |
| PR-10 | Thử nghiệm model/JEV có so sánh baseline | Có dữ liệu đủ điều kiện và baseline đã đo | 5–10 cho một vòng thử |

PR-04 có thể phát triển với fixture song song PR-02/03, nhưng chỉ được nghiệm thu
corpus thật sau phê duyệt. PR-07 có thể dựng UI bằng fixture sau PR-01. PR-09/10
không nằm trên đường hoàn thành bản dùng thử tìm sự kiện + FAQ; điều đó không tự
bỏ các release_blocker đang khai báo trong cấu hình hiện tại.

## 6. Chi tiết và tiêu chí hoàn thành

### PR-00 — Khóa baseline

- [x] Sửa việc tách số lượng khỏi q ở đầu/giữa/cuối câu; giữ số thuộc tên sự kiện.
- [x] Test câu không có keyword, ghế/vé, số 1/20/ngoài phạm vi, tên chứa 2026 và
  lượt làm rõ ngân sách. Assert state và arguments; application smoke thực thi
  trực tiếp coroutine có gateway giả, không thay cho pytest HTTP/async.
- [x] Bổ sung `loop/**` cho OBS-02; giữ các sửa đổi hiện tại trong working tree.
- [ ] Có CI run hợp lệ cho đúng head và hoàn tất gate còn thiếu. Không dùng git
  restore/ghi đè để làm sạch bản vá; không push/merge khi chưa được giao.
- [x] Local Python 3.12: compile/static/config/schema/lock, Ruff/format, Mypy,
  full pytest 348 test với coverage 92,47% (pytrace), integrity, pip check và
  wheel build; knowledge smoke TEST_ONLY.
- [ ] CI matrix Windows/Linux Python 3.11/3.12, advisory, wheel cài ở môi trường
  sạch và Docker smoke cho bản vá hiện tại.
- Hoàn thành khi không còn must-fix của baseline và có bằng chứng cho đúng head.
  BLOCKED_ENV/NOT_RUN phải được giải quyết trên runner khác, không đổi thành PASS.

### PR-01 — Hợp đồng và quyền sở hữu

- Chốt journey/golden conversations: search, sửa/xóa điều kiện, xem thêm, chọn
  ứng viên, detail, policy, dữ liệu riêng tư khi chưa đăng nhập và yêu cầu mutation.
- Thiết kế các kết quả typed (EventSummary/EventDetail/EventPage, citations,
  actions, giới hạn/cảnh báo snapshot) ở domain/application; Pydantic chỉ ở inbound.
- Chốt DTO tăng thêm có version, giới hạn số item/độ dài, tương thích consumer,
  trường hợp không đủ dữ liệu và capability đang tắt. Không trả raw DTO backend.
- Xác minh API backend ở SHA cụ thể: endpoint, envelope, fields/types/nullability,
  phân trang, ngày giờ/timezone, mã lỗi, public visibility và side effects.
- Chốt BFF giữ phiên và candidate refs với TTL; state không phải định danh.
- Hoàn thành khi AI/backend/BFF dùng cùng contract fixtures và test tương thích;
  hợp đồng mới đặt trong configs, không sửa schema lịch sử v1.2.

### PR-02 — GET search/detail và bằng chứng READ_ONLY

- Thực hiện use case đọc qua gateway, DTO projection và xử lý lỗi có cấu trúc.
- Dùng sandbox backend: anonymous PUBLISHED được đọc, DRAFT/unpublished bị từ chối,
  ID không tồn tại/khác phạm vi không thành dữ liệu hợp lệ.
- Assert fixed GET/path/query, không credential thừa, không redirect/retry,
  cap bytes/time/results và response schema; GET side effect vẫn bị chặn.
- Thu network trace và snapshot DB test trước/sau phiên. Không gọi endpoint ghi
  để chuẩn bị fixture từ chatbot; QA/backend chuẩn bị fixture qua harness riêng.
- Hoàn thành khi PUBLIC-SEARCH/PUBLIC-DETAIL/RUNTIME-READONLY có bằng chứng thực
  và owner review. Test double không cấp quyền bật tool; config mặc định vẫn tắt.

### PR-03 — Luồng người dùng hoàn chỉnh

- Trả cards/data đã allowlist: người dùng biết tìm được sự kiện nào và có cách
  mở trang/xem chi tiết. Không chỉ trả số đếm như hiện tại.
- Nhận diện EVENT_DETAIL/chọn item, giải quyết tham chiếu bằng candidate refs,
  validate ID và GET lại PUBLISHED trước khi trả lời.
- Phân trang có page bounds, giữ nguyên query/filter; đổi filter thì reset page.
  Xử lý hết trang, trang vượt cuối và pagination_limited.
- Composer/API giữ has_more/has_previous/result_complete/capped; không biến trang
  cuối thành khẳng định đã đọc toàn bộ kết quả.
- Hỗ trợ các lượt sửa quantity/budget/scope theo tác vụ đang chạy và task switch;
  filter chưa hỗ trợ phải được giải thích/làm rõ, không âm thầm bỏ qua.
- Actions chỉ là route/template nội bộ từ registry được duyệt. Không mở checkout
  khi không có reservation từ UI chính; không thực hiện giao dịch.
- Cập nhật test_unused_tools_locked khi thêm caller: khóa theo capability rõ ràng
  và behavior, không chỉ sửa con số 13 để làm test xanh.
- Hoàn thành khi golden conversations chạy qua HTTP và BFF, gồm lỗi upstream và
  hết kết quả; không nhận ID/quyền do model tự khai làm bằng chứng truy cập.

### PR-04 — RAG có nội dung thật

- Policy owner cung cấp nguồn canonical, approval, audience, version, thời hiệu,
  người chịu trách nhiệm và quy trình thu hồi. Không dùng draft làm chính sách thật.
- Bổ sung bộ câu hỏi độc lập theo nhóm paraphrase, có không dấu, ngoài phạm vi,
  no-evidence, điều kiện/ngoại lệ và tham chiếu chéo section/tài liệu.
- Mở rộng routing FAQ theo phạm vi corpus đã duyệt. Câu hỏi về giá/tồn kho/order
  không được thay bằng thông tin policy tĩnh.
- Đo source recall, clause/evidence completeness, citation validity/faithfulness,
  abstention và latency. Không dùng source-set accuracy hoặc confidence proxy
  để suy ra nội dung trả lời đã đúng/đủ.
- Chốt tập và ngưỡng trước đo; đề xuất khởi điểm Recall@5 >=0,90, citation hợp lệ
  100%, không leak nguồn bị cấm. Đây là ngưỡng đề xuất, chưa được owner phê duyệt.
- Kiểm tra revoke/expiry/corrupt catalog tại thời điểm trả lời, cross-section
  ngoại lệ, câu trả lời quá dài và rollback không phục hồi nguồn đã thu hồi.
- Hoàn thành khi RAG-APPROVED-CORPUS/RAG-READONLY có hồ sơ và evaluation thật;
  default disabled được giữ trong source và packaged fallback.

### PR-05 — Dữ liệu con và snapshot

- Owner backend chứng minh PUBLISHED parent guard và event–area–type–phase–seat
  membership. Path ID hoặc chỉ annotation GetMapping không phải bằng chứng đủ.
- Đối chiếu schema với mẫu live đã khử dữ liệu nhạy cảm; phân biệt unknown với 0.
  Không coi row thiếu status/field bắt buộc là bằng chứng không còn ghế.
- Snapshot có thời điểm nguồn và thời điểm đọc, timezone, provenance, completeness
  và giới hạn. Timestamp nhận response không tự chứng minh dữ liệu gốc còn tươi.
- Inventory thiếu timestamp, list bị cap hoặc nhiều request không có bảo đảm
  nhất quán phải được đánh dấu chưa đủ điều kiện để tư vấn chắc chắn.
- Hoàn thành khi PUBLISHED-CHILD và RUNTIME-READONLY có integration negatives và
  snapshot đạt hợp đồng; child tools vẫn mặc định disabled.

### PR-06 — Tư vấn vé xác định

- Mở rộng TicketOption/Snapshot/Recommendation bằng value objects và port đủ
  thông tin; sau đó mới nối recommend vào application/bootstrap.
- Quy đổi TOTAL/PER_TICKET theo quantity bằng Decimal; kiểm tra VND/currency,
  phase window/status, quantity, mức giá và giới hạn đơn.
- Áp dụng quota/seat chỉ khi dữ liệu đủ và được phép đọc. Không giả định đã biết
  quota cá nhân nếu chưa xác thực; trường hợp thiếu điều kiện phải báo giới hạn.
- Chưa hỗ trợ tổ hợp nhiều hạng vé thì nói rõ phạm vi; không gọi việc sắp giá đơn
  giản là nghiệm thu đầy đủ bài toán tối ưu tổ hợp.
- Golden cases: thiếu dữ liệu, stale/capped snapshot, hết phase, không đủ chỗ,
  vượt quota, ngân sách sát biên, ghế liền nhau nếu scope có, và tie-break ổn định.
- Hoàn thành khi đề xuất có giải thích và nguồn snapshot, không hứa giữ chỗ hoặc
  bảo đảm inventory lúc người dùng thanh toán; live optimizer gate được review.

### PR-07 — BFF và UI

- Owner frontend/BFF triển khai contract cards, citations, cảnh báo giới hạn,
  điều hướng, trạng thái loading/error và bộ thao tác làm rõ.
- Chốt ownership state, candidate TTL, reset/task switch, request ID và privacy
  retention. Không dùng conversation_id làm session auth.
- Error/retry của UI không kích hoạt business write; timeout có phản hồi rõ và
  không mất tiêu chí hội thoại. Refresh/token/session dùng cơ chế nền tảng đã duyệt.
- Hoàn thành khi hành trình chạy từ UI tới AI và backend test, gồm chưa đăng nhập,
  double-click, timeout và dữ liệu bị thu hồi giữa hai lượt.

### PR-08 — Tài nguyên, quan sát và phát hành

- Giới hạn byte body trước JSON parsing, kiểm tra cả chunked body và Content-Length
  sai. Field max_length không thay thế body cap. Ngưỡng cụ thể chốt trong contract.
- Rate limit tại perimeter/BFF và admission limit trong service; giới hạn toàn hệ
  thống phải tính nhiều worker, không chỉ một process.
- Bounded worker/queue và ngân sách cho RAG. Kiểm chứng cả công việc nền còn chạy
  sau timeout: timeout response của to_thread không chứng minh worker đã dừng.
- Cache nội dung/index chỉ đọc theo release hash nếu benchmark chứng minh cần;
  mỗi request vẫn kiểm tra authority/gate/revocation, không cache quyền cũ.
- Đo latency từng chặng, queue saturation, timeout/error/abstention, CPU/RAM;
  không log message/state/token/QR/raw backend JSON. Chốt SLO theo máy đích rồi đo
  tải, thay vì công bố một mức RPS chưa đo.
- Container non-root, corpus/config mount read-only, kiểm tra network/credential
  scope, secret handling, health contract và rollback theo release.
- Hoàn thành khi đúng release profile có đủ gate kỹ thuật, integration, security
  và performance; archived evidence gắn head/config/backend/corpus revisions.

### PR-09 — Đọc tài khoản (mốc mở rộng)

- Thiết kế delegation dựa trên identity nền tảng đã xác minh: issuer/audience,
  expiry, customer scope và service channel; không tự lấy userId từ state/model.
- Backend là nơi quyết định ownership. Từ chối admin/service impersonation,
  credential không hợp lệ và cross-account A/B.
- Use case đọc reservation/order/payment/my-tickets/refund-review chỉ được nối
  khi có bằng chứng cho từng tool; projection loại QR/token/payment URL/PII thừa.
- Hoàn thành khi PRIVATE-SELF-AUTH/SAFE-TICKETS/RUNTIME-READONLY cùng đạt các bằng
  chứng tương ứng. Không thêm mutation hoặc tái sử dụng generic proxy.

### PR-10 — Model và JEV (thử nghiệm tùy chọn)

- Tạo dữ liệu đủ đa dạng, gán nhãn và chia tách group/family trước huấn luyện;
  12 record hiện có không đủ cho kết luận chất lượng.
- Nếu cần nhãn/schema mới thì tạo contract mới dưới configs, không sửa v1.2.
- So sánh model gốc/fine-tune/rule-based trên held-out và golden conversations:
  intent/slots, hallucination, abstention, latency/RAM, injection và lỗi JSON.
- Model chỉ xuất Understanding được validate, không nhận network/SQL/tool tùy ý.
  Fallback có budget xác định và không được nới gate.
- Chỉ xem xét JEV/semantic/reranker/generation khi có cải thiện đo được và đáp ứng
  ngân sách tài nguyên. Ghi model/data/config/run hashes; không ép dùng đủ mọi
  công nghệ chỉ vì đã xuất hiện trong kiến trúc lịch sử.

## 7. Các mốc nghiệm thu

| Mốc | Phạm vi hoàn thành | Điều chưa được suy ra |
|---|---|---|
| M0 | Baseline qua PR-00, full gate kỹ thuật có bằng chứng | Chưa được mở tool live |
| M1 | PR-01/02/03: tìm–xem thêm–chọn–chi tiết công khai | Chưa có đề xuất vé/tài khoản |
| M2 | PR-04: policy có nguồn thật; PR-07: hành trình UI | Chưa phải production-ready nếu PR-08/gate còn thiếu |
| M3 | PR-05/06: dữ liệu con và đề xuất theo snapshot đủ điều kiện | Không tạo giữ chỗ/giao dịch, không hứa inventory realtime |
| M4 | PR-08 và release profile được duyệt | Không tự mở private/model chưa nghiệm thu |
| M5 | PR-09/10 theo nhu cầu và evidence | Không mở quyền ghi ở bất kỳ phiên bản nào |

MVP tìm sự kiện + detail + FAQ + UI: ước lượng 16–28 ngày công AI theo các PR liên
quan; thêm child reads/optimizer khoảng 6–10 ngày công. Đây không phải lịch elapsed
hoặc cam kết production; phụ thuộc ngoài AI có thể là đường găng.

Các gate có release_blocker=true trong cấu hình hiện tại vẫn giữ nguyên. Nếu chủ
dự án muốn một release chỉ có chức năng công khai, cần ADR/release profile riêng
nêu phạm vi và điều kiện, không âm thầm bỏ gate private hoặc đổi BLOCKED thành PASS.
Bản dùng thử có kiểm soát và bản phát hành production phải ghi trạng thái khác nhau.

## 8. Đầu vào và chủ sở hữu cần chốt

| Đầu vào | Owner theo vai trò | Chặn công việc |
|---|---|---|
| Backend SHA/OpenAPI, test deployment và seeded fixtures | Backend + QA | PR-01/02/05/09 |
| Trace zero-write và snapshot DB test | Backend + QA/security | Mở mọi business tool |
| Corpus canonical và approval/thu hồi | Policy owner | PR-04 serving thật |
| Bộ câu hỏi/điều khoản chuẩn, held-out riêng | Policy owner + QA | Nghiệm thu RAG/model |
| BFF session, route UI và delegation | Frontend/BFF + security | PR-01/07/09 |
| Runner Windows/Linux, Docker và advisory access | Release/infra | PR-00/08 |
| Máy đích, SLO và mức tải dự kiến | Infra + chủ dự án | PR-08, chọn model/index |

Không suy đoán assignee cụ thể. Khi bắt đầu từng PR phải ghi người phụ trách,
phụ thuộc đã nhận, bằng chứng cần có và định nghĩa hoàn thành.

## 9. Việc nên làm ngay

1. PR-00: REV-01 và trigger CI đã sửa local; xác nhận CI cho đúng head và hoàn tất
   các gate CI matrix/advisory/clean-wheel/Docker còn thiếu ở runner đủ quyền.
2. PR-01: chốt DTO và hành trình với backend/BFF, pin API thật. Trong khi chờ có
   thể xây use case/contract fixtures default-disabled, không báo tích hợp PASS.
3. Bắt đầu thu corpus và bộ đánh giá thật cho PR-04 song song. Đây là phụ thuộc
   nội dung, không giải quyết bằng cách tự đổi trạng thái draft thành approved.

Các thay đổi kế hoạch nằm trong repo AI Service. Việc sửa backend/web/infra,
commit/push/merge hoặc enable feature là công việc riêng theo phạm vi được giao.
