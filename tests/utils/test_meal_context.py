import pytest

from app.utils.kakao import KakaoError
from app.utils.meal import MENU_CONTEXT_ERROR_MESSAGE, save_menu


def test_save_menu_raises_kakao_error_when_context_is_missing() -> None:
    with pytest.raises(KakaoError) as exc_info:
        save_menu([], "lunch_menu", "산돌식당", ["김치찌개"])

    assert exc_info.value.message == MENU_CONTEXT_ERROR_MESSAGE
