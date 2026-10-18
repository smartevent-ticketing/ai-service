# 11 - Quy trình làm việc dành cho Coding Agent và Audit Agent

## 0. Phân biệt quyền

- Coding Agent thay đổi **source code** theo yêu cầu phát triển, trên branch riêng và qua review.
- AI chatbot do code đó tạo ra **chỉ có quyền đọc business data**; không được tạo công cụ ghi.
- Không sửa dữ liệu nghiệp vụ thật khi kiểm thử; mọi kiểm thử có thay đổi sử dụng test environment riêng.

## 1. Coding Agent - trước khi code

1. Xác nhận repository và branch.
2. Đọc `AGENTS.md` cấp root và AGENTS riêng của repo nếu có.
3. Kiểm tra working tree/status.
4. Xác định feature slice và dependency.
5. Mở code thật của API/state/DTO liên quan.
6. Lập change plan: files, contracts, tests, migrations, docs.
7. Nếu yêu cầu mâu thuẫn source-of-truth, dừng và nêu conflict thay vì tự chọn im lặng.

## 2. Trong khi code

- Không refactor ngoài scope nếu không cần.
- Giữ typed contracts.
- Thêm test cùng thay đổi.
- Không log credentials/full private payload.
- **Chatbot runtime tuyệt đối không được gọi mutation nghiệp vụ**; coding agent chỉ được sửa code/test/docs theo nhiệm vụ, không chạy mutation trên dữ liệu thật.
- Nếu API backend đổi, cập nhật OpenAPI/generated FE types.
- Nếu architecture decision đổi, thêm ADR/decision record.

## 3. Sau khi code

### AI Service

Chạy lint/type/test, dataset/schema validation và eval subset liên quan.

### Backend

Chạy Gradle tests liên quan và integration tests nếu thay đổi transaction/state/API.

### Web

Chạy `npm run check`.

### Infra

Validate compose/config, không phá local bind/security assumptions.

## 4. Audit Agent

Audit theo thứ tự:

1. Scope compliance.
2. Architecture boundaries.
3. Security/authorization và **deny-by-default GET-only**.
4. Business invariants.
5. Data consistency/stale data.
6. Error/retry cho GET; chặn toàn bộ mutation (không có ngoại lệ idempotency).
7. Tests/evidence.
8. Documentation drift.
9. Performance/cost risks.

Severity:

- P0: security/data integrity/cross-account/payment/oversell critical.
- P1: release blocker, incorrect core flow, missing auth/idempotency.
- P2: reliability/maintainability/coverage gap.
- P3: polish/documentation/style.

## 5. Báo cáo audit bắt buộc

Mỗi finding phải có:

- severity;
- repository + path;
- behavior/risk;
- reproducible evidence hoặc code evidence;
- expected behavior;
- recommended fix;
- test cần thêm.

Không ghi finding chung chung kiểu “nên tối ưu AI”.

## 6. Agent không được tự tuyên bố

Không nói:

- production-ready;
- secure;
- scalable;
- accurate;
- merge-ready;

nếu chưa có evidence tương ứng. Nêu rõ phạm vi evidence đã chạy.
