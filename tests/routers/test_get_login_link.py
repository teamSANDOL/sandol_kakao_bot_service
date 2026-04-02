from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from app.routers import user as user_router_module
from app.routers.user import user_router
from app.schemas.auth import IssueLinkRes
from app.utils.db import get_db
from app.utils.http import get_async_client
from app.utils.kakao import KakaoError, parse_payload


def make_payload() -> SimpleNamespace:
    return SimpleNamespace(
        user_request=SimpleNamespace(
            user=SimpleNamespace(
                id="kakao-user-1",
                properties=SimpleNamespace(
                    plusfriend_user_key="plusfriend-user-1",
                    app_user_id="app-user-1",
                ),
            )
        )
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(user_router)

    @app.exception_handler(KakaoError)
    async def handle_kakao_error(_, exc: KakaoError) -> JSONResponse:
        return JSONResponse({"message": exc.message})

    async def fake_parse_payload():
        return make_payload()

    async def fake_get_db():
        yield None

    async def fake_get_async_client():
        yield None

    async def fake_generate_login_link(*_: object, **__: object) -> IssueLinkRes:
        return IssueLinkRes(login_link="https://example.com/login", expires_in=300)

    async def fake_make_login_link_response(*_: object, **__: object) -> SimpleNamespace:
        return SimpleNamespace(
            get_dict=lambda: {
                "status": "ok",
                "login_link": "https://example.com/login",
            }
        )

    app.dependency_overrides[parse_payload] = fake_parse_payload
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[get_async_client] = fake_get_async_client

    monkeypatch.setattr(
        user_router_module, "generate_login_link", fake_generate_login_link
    )
    monkeypatch.setattr(
        user_router_module, "make_login_link_response", fake_make_login_link_response
    )

    return TestClient(app)


def test_get_login_link_allows_relogin_when_existing_user_session_is_inactive(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find_user(*_: object, **__: object) -> SimpleNamespace:
        return SimpleNamespace(id=1)

    monkeypatch.setattr(user_router_module, "find_user", fake_find_user)
    monkeypatch.setattr(user_router_module, "has_active_login_session", lambda _: False)

    response = client.post("/users/get_login_link", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_login_link_blocks_user_with_active_login_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find_user(*_: object, **__: object) -> SimpleNamespace:
        return SimpleNamespace(id=1)

    monkeypatch.setattr(user_router_module, "find_user", fake_find_user)
    monkeypatch.setattr(user_router_module, "has_active_login_session", lambda _: True)

    response = client.post("/users/get_login_link", json={})

    assert response.status_code == 200
    assert response.json()["message"] == "이미 로그인된 사용자입니다."
