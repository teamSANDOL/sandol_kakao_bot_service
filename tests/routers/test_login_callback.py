from types import SimpleNamespace
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import jwt
import pytest

from app.config import Config
from app.routers import user as user_router_module
from app.routers.user import user_router
from app.schemas.auth import LoginCallbackReq
from app.services.auth_service import sign_payload
from app.utils.db import get_db


def make_access_token(**overrides: object) -> str:
    claims = {
        "sub": "keycloak-sub-1",
        "iss": f"{Config.KC_SERVER_URL}realms/{Config.KC_REALM}",
        "aud": "account",
        "azp": Config.KC_CLIENT_ID,
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, "unused-secret", algorithm="HS256")


def make_callback_payload(**overrides: object) -> LoginCallbackReq:
    payload = {
        "issuer": f"{Config.KC_SERVER_URL}realms/{Config.KC_REALM}",
        "aud": Config.KC_CLIENT_ID,
        "chatbot_user_id": "kakao-user-1",
        "client_key": Config.KC_CLIENT_ID,
        "relay_access_token": make_access_token(),
        "offline_refresh_token": "refresh-token",
        "expires_in": 300,
        "refresh_expires_in": 3600,
        "ts": int(time.time()),
        "nonce": f"nonce-{time.time_ns()}",
    }
    payload.update(overrides)
    return LoginCallbackReq.model_validate(payload)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(user_router)

    async def fake_get_db():
        yield None

    async def fake_map_keycloak_user(**_: object) -> SimpleNamespace:
        return SimpleNamespace(
            id=1, kakao_id="kakao-user-1", keycloak_id="keycloak-sub-1"
        )

    app.dependency_overrides[get_db] = fake_get_db
    monkeypatch.setattr(user_router_module, "map_keycloak_user", fake_map_keycloak_user)
    return TestClient(app)


def test_login_callback_returns_ok_for_valid_callback(client: TestClient) -> None:
    payload = make_callback_payload()

    response = client.post(
        "/users/callback",
        json=payload.model_dump(mode="json"),
        headers={
            "X-Relay-Signature": sign_payload(payload, Config.RELAY_CLIENT_SECRETS)
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_callback_rejects_invalid_callback_audience(client: TestClient) -> None:
    payload = make_callback_payload(aud="other-client")

    response = client.post(
        "/users/callback",
        json=payload.model_dump(mode="json"),
        headers={
            "X-Relay-Signature": sign_payload(payload, Config.RELAY_CLIENT_SECRETS)
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_callback_audience"
