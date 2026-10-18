# 05 - Ontology hội thoại và chính sách điều phối

## 1. Intent V1

| Domain | Intent |
|---|---|
| General | GREETING, OUT_OF_SCOPE, CLARIFY |
| Event | SEARCH_EVENT, EVENT_DETAIL, EVENT_COMPARE |
| Ticket | TICKET_PRICE, TICKET_AVAILABILITY, SEAT_AVAILABILITY, TICKET_RECOMMEND, TICKET_ALTERNATIVE |
| Booking | BOOKING_GUIDANCE, RESERVATION_STATUS, CHECKOUT_HANDOFF |
| Account | ORDER_STATUS, PAYMENT_STATUS, MY_TICKETS |
| Support | REFUND_POLICY, REFUND_SUPPORT, TICKET_TRANSFER_HELP, HUMAN_HANDOFF |

Model có thể xuất `primary_intent` và `secondary_intents` để xử lý câu đa mục tiêu.

## 2. Slot chính

### Event
- `event_id`
- `event_name`
- `category_id/category_name`
- `city`
- `date_start/date_end`

### Ticket/booking
- `quantity`
- `ticket_type_id/ticket_type_name`
- `sale_phase_id`
- `preferred_area_id`
- `preferred_row`
- `seat_preference`

### Budget
- `amount`
- `currency`
- `scope`: `TOTAL`, `PER_TICKET`, `UNKNOWN`

### Account/reference
- `order_id`
- `order_code`
- `selected_candidate_id`
- `referenced_result_index`

## 3. State Delta operations

- `SET`: gán/thay giá trị.
- `REMOVE`: xóa một slot.
- `ADD`: thêm preference/exclusion.
- `CLEAR`: xóa một nhóm state.
- `REFER`: trỏ tới object/candidate đã hiển thị.
- `SWITCH_TASK`: chuyển active task.

Không để model viết lại toàn bộ state mỗi lượt. Công thức mục tiêu:

`S(t+1) = ValidateMerge(S(t), Delta(t))`.

## 4. Ví dụ correction

State cũ:

```json
{"city":"Hà Nội","quantity":2,"budget_amount":1200000,"budget_currency":"VND","budget_scope":"TOTAL"}
```

User: “Đổi thành ba vé nhưng giữ ngân sách.”

Delta chuẩn:

```json
{"state_delta":[{"operation":"SET","slot":"quantity","value":3}]}
```

Không lặp lại city/budget nếu không thay đổi.

## 5. Ambiguity policy

Hỏi lại khi mơ hồ **có ảnh hưởng materially tới hành động**.

Ví dụ “Tầm một triệu cho 2 người” có thể chưa rõ TOTAL hay PER_TICKET; hỏi lại trước tối ưu theo giá.

Không hỏi nếu có thể thực hiện một search rộng an toàn. Ví dụ “Có sự kiện âm nhạc cuối tuần này không?” không bắt buộc quantity.

## 6. Reference resolution

Câu “cái thứ hai”, “vé đó”, “sự kiện này” chỉ resolve khi conversation state có candidate mapping rõ ràng. Nếu reference có nhiều ứng viên, hỏi lại. Không để LLM chọn ngẫu nhiên.

## 7. Dialogue Policy

Policy có thứ tự kiểm tra:

**Đặc biệt:** `state_delta` chỉ sửa dữ liệu hội thoại của AI; không được gửi tới API ghi của SmartEvent. Chọn action có vẻ là POST/PUT/PATCH/DELETE phải bị policy map sang `EXPLAIN_WRITE_LIMITATION` hoặc `NAVIGATE_TO_BOOKING`.

1. Safety/system constraints.
2. Authentication/authorization requirements.
3. Quyền READ_ONLY — mọi yêu cầu mutation bị từ chối hoặc chuyển sang hướng dẫn UI.
4. Missing material information.
5. Valid state transition.
6. Tool GET-only availability/budget.
7. Optional model recommendation.

Model `proposed_action` chỉ là đề xuất; code Policy Engine quyết định action thực tế.

## 8. Proposed actions V1

- `ANSWER_GREETING`
- `ASK_CLARIFICATION`
- `SEARCH_EVENTS`
- `GET_EVENT_DETAILS`
- `GET_TICKET_OPTIONS`
- `CHECK_INVENTORY`
- `CHECK_SEATS`
- `RUN_TICKET_OPTIMIZER`
- `RETRIEVE_POLICY`
- `REQUEST_LOGIN`
- `GET_MY_ORDERS`
- `GET_PAYMENT_STATUS`
- `GET_MY_TICKETS`
- `NAVIGATE_TO_BOOKING` (điều hướng giao diện, không gọi backend tool)
- `EXPLAIN_WRITE_LIMITATION` (giải thích AI không thao tác thay người dùng)
- `SHOW_SUPPORT_CHANNEL` (chỉ hiển thị kênh/liên kết, không tạo ticket)
- `REFUSE_UNSUPPORTED_ACTION`

## 9. Conversation memory

Phân biệt:

- **Recent messages:** hội thoại gần nhất.
- **Dialogue state:** giá trị đang còn hiệu lực.
- **Candidate references:** object đã hiển thị để resolve pronoun/index.
- **Business state:** luôn nằm ở backend, không “nhớ” như fact lâu dài.
- **Long-term preference:** chưa bắt buộc V1; chỉ lưu khi có product/privacy decision riêng.

## v1.2 — Cấu trúc slot chuẩn và phân biệt decision/action

Canonical state, entities và state_delta sử dụng **flat slot names** khai báo trong `configs/dialogue_ontology.yaml`. Không sử dụng object lồng `budget` trong dữ liệu SFT. Chuyển `budget.amount → budget_amount`, `budget.scope → budget_scope`, `budget.currency → budget_currency` tại UI adapter nếu frontend cần DTO lồng. `active_intent` là slot điều khiển nội bộ. Operation `ADD` chỉ dùng cho `excluded_preferences`; `REFER` chỉ `selected_candidate_id`; `SWITCH_TASK` chỉ `active_intent`. `CLEAR` sử dụng ba group `ALL_SLOTS`, `EVENT_FILTERS`, `TICKET_PREFERENCES`, không tạo state key tương ứng. Model chỉ đề xuất, policy quyết định và tool gate có thể từ chối.
