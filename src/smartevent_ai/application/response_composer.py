"""Deterministic response composition for the bootstrap dialogue workflow."""

from smartevent_ai.domain.dialogue import ClarificationReason, Intent


class ResponseComposer:
    def clarification(self, reason: ClarificationReason | None) -> str:
        if reason is ClarificationReason.DATE_INVALID:
            return "Vui lòng cho biết tháng hoặc khoảng thời gian hợp lệ để tìm sự kiện."
        if reason is ClarificationReason.MODEL_OUTPUT_INVALID:
            return "Tôi chưa hiểu chắc điều kiện này. Bạn vui lòng diễn đạt lại yêu cầu."
        if reason is ClarificationReason.QUANTITY_REQUIRED:
            return "Tổng ngân sách này dành cho bao nhiêu vé?"
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
        if count == 0:
            return "Không có sự kiện khớp các điều kiện này. Bạn có thể đổi thành phố, thời gian hoặc ngân sách."
        if (
            result.get("has_more")
            or result.get("pagination_limited")
            or result.get("capped_by_adapter")
        ):
            return (
                f"Đã tìm được {count} sự kiện phù hợp trong phần kết quả hiện tại; "
                "còn kết quả chưa xem. Hãy thu hẹp điều kiện tìm kiếm."
            )
        return (
            f"Đã đọc được {count} sự kiện từ backend. "
            "Hãy mở trang sự kiện để xem chi tiết và chọn vé."
        )

    def static_answer(self, intent: Intent) -> str:
        answers = {
            Intent.ORDER_STATUS: (
                "Tôi không có quyền xem dữ liệu tài khoản khi chưa xác thực và nghiệm thu kết nối. "
                "Vui lòng xem trong tài khoản SmartEvent."
            ),
            Intent.PAYMENT_STATUS: (
                "Tôi không có quyền xem dữ liệu tài khoản khi chưa xác thực và nghiệm thu kết nối. "
                "Vui lòng xem trong tài khoản SmartEvent."
            ),
            Intent.MY_TICKETS: (
                "Tôi không có quyền xem dữ liệu tài khoản khi chưa xác thực và nghiệm thu kết nối. "
                "Vui lòng xem trong tài khoản SmartEvent."
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
