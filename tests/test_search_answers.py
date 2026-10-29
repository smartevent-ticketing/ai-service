from smartevent_ai.application.response_composer import ResponseComposer


def test_search_lists_only_projected_event_facts_in_vietnam_time() -> None:
    answer = ResponseComposer().search_result(
        {
            "data": [
                {
                    "name": "Acoustic cuối năm",
                    "city": "Hồ Chí Minh",
                    "startTime": "2026-11-01T12:00:00Z",
                    "description": "DO NOT DISPLAY",
                }
            ]
        }
    )
    assert "Acoustic cuối năm" in answer and "Hồ Chí Minh" in answer
    assert "01/11/2026 19:00" in answer
    assert "DO NOT DISPLAY" not in answer


def test_search_empty_and_partial_are_distinguished() -> None:
    composer = ResponseComposer()
    assert "Chưa tìm thấy" in composer.search_result({"data": []})
    answer = composer.search_result({"data": [], "has_more": True})
    assert "còn kết quả chưa xem" in answer
    assert "Chưa tìm thấy" not in answer


def test_search_does_not_guess_an_invalid_or_naive_time() -> None:
    answer = ResponseComposer().search_result(
        {
            "data": [
                {"name": "A", "startTime": "bad-date"},
                {"name": "B", "startTime": "2026-11-01T12:00:00"},
            ]
        }
    )
    assert "bad-date" not in answer
    assert "01/11" not in answer
