from starlette.requests import Request
import pytest

from main import app, login_required_error_handler
from app.utils.kakao import (
    KakaoError,
    LoginRequiredError,
    NotAuthenticated,
    UserIdentityConflictError,
)


def make_request(path: str = "/users/info") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "route": None,
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_login_required_handler_returns_kakao_response() -> None:
    response = await login_required_error_handler(
        make_request(),
        LoginRequiredError(message="로그인 필요"),
    )

    assert response.status_code == 200
    assert b"\xeb\xa1\x9c\xea\xb7\xb8\xec\x9d\xb8" in response.body


def test_app_registers_specific_kakao_exception_handlers() -> None:
    assert LoginRequiredError in app.exception_handlers
    assert NotAuthenticated in app.exception_handlers
    assert KakaoError in app.exception_handlers
    assert UserIdentityConflictError in app.exception_handlers
