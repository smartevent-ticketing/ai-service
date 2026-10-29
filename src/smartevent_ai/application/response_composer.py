"""Deterministic response composition for the bootstrap dialogue workflow."""

from datetime import datetime, timedelta, timezone

from smartevent_ai.domain.dialogue import ClarificationReason, Intent


class ResponseComposer:
    def clarification(self, reason: ClarificationReason | None) -> str:
        if reason is ClarificationReason.BUDGET_SCOPE:
            return "Ngân sách này tính cho mỗi vé hay tổng tất cả vé?"
        if reason is ClarificationReason.BUDGET_OUT_OF_RANGE:
            return "Ngân sách nằm ngoài phạm vi hỗ trợ. Vui lòng nhập số tiền từ 0 đến 1 tỷ đồng."
        if reason is ClarificationReason.QUANTITY_OUT_OF_RANGE:
            return "Vui lòng chọn số lượng từ 1 đến 20 vé để tiếp tục tư vấn."
        return "Tôi cần thêm thông tin để hiểu chính xác yêu cầu của bạn."

    def search_result(self, result: dict[str, object]) -> str:
        data = result.get("data")
        count = len(data) if isinstance(data, list) else 0
        if (
            result.get("has_more")
            or result.get("pagination_limited")
            or result.get("capped_by_adapter")
        ):
            heading = (
                f"Đã tìm được {count} sự kiện phù hợp trong phần kết quả hiện tại; "
                "còn kết quả chưa xem. Hãy thu hẹp điều kiện tìm kiếm."
            )
        elif count == 0:
            return "Chưa tìm thấy sự kiện đã công bố phù hợp với điều kiện tìm kiếm."
        else:
            heading = f"Tìm thấy {count} sự kiện đã công bố:"
        lines = [heading]
        if isinstance(data, list):
            for item in data[:10]:
                if not isinstance(item, dict):
                    continue
                name = " ".join(str(item.get("name", "Sự kiện")).split())[:255]
                city = " ".join(str(item.get("city") or "").split())[:80]
                details = [name]
                if city:
                    details.append(city)
                start = item.get("startTime")
                if isinstance(start, str):
                    try:
                        when = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        if when.tzinfo is not None:
                            details.append(
                                when.astimezone(timezone(timedelta(hours=7))).strftime(
                                    "%d/%m/%Y %H:%M"
                                )
                            )
                    except ValueError:
                        pass
                lines.append("• " + " — ".join(details))
        lines.append("Thời gian hiển thị theo giờ Việt Nam. Mở trang sự kiện để xem chi tiết.")
        return "\n".join(lines)

    def static_answer(self, intent: Intent) -> str:
        answers = {
            Intent.PUBLIC_HELP: (
                "Hiện chưa có đủ tài liệu hướng dẫn đã được xác minh cho câu hỏi này. "
                "Bạn có thể nói rõ nội dung muốn tìm hiểu hoặc xem hướng dẫn trên giao diện SmartEvent."
            ),
            Intent.ORDER_STATUS: (
                "Bạn mở Tài khoản → Đơn hàng để xem trạng thái đơn của mình. "
                "Trợ lý hiện chưa hỗ trợ tra cứu đơn hàng cá nhân ngay trong hội thoại."
            ),
            Intent.PAYMENT_STATUS: (
                "Bạn mở Tài khoản → Đơn hàng và chọn đơn cần kiểm tra thanh toán. "
                "Tôi chưa thể xác nhận trạng thái giao dịch cá nhân trong hội thoại này."
            ),
            Intent.MY_TICKETS: (
                "Bạn đăng nhập và mở mục Vé trong trang Tài khoản để xem vé đã mua. "
                "Trợ lý hiện chưa hỗ trợ đọc danh sách vé cá nhân ngay trong hội thoại."
            ),
            Intent.REFUND_POLICY: (
                "Tôi chỉ hỗ trợ tra cứu chính sách đã được phê duyệt. Hiện chưa có nguồn chính sách "
                "đủ điều kiện; vui lòng xem trang hỗ trợ chính thức."
            ),
            Intent.BOOKING_GUIDANCE: (
                "Tôi có thể hướng dẫn chọn vé, nhưng không giữ, đặt, hủy hoặc thanh toán thay bạn. "
                "Hãy thao tác trên giao diện SmartEvent."
            ),
            Intent.TICKET_RECOMMEND: (
                "Tôi đã ghi nhận tiêu chí trong phiên hội thoại này, nhưng chưa có tồn kho được xác minh "
                "để đề xuất vé."
            ),
            Intent.GREETING: (
                "Xin chào. Tôi có thể giúp tìm hiểu sự kiện hoặc hướng dẫn mua vé mà không thực hiện "
                "giao dịch thay bạn."
            ),
        }
        return answers.get(intent, "Bạn muốn tìm sự kiện, tìm hiểu giá vé hay hỏi về đơn hàng?")
