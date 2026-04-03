import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import Config
from app.schemas.auth import LoginCallbackReq
from app.services.auth_service import (
    extract_keycloak_sub,
    validate_login_callback_claims,
    verify_timestamp,
)


def make_callback_payload(**overrides: object) -> LoginCallbackReq:
    payload = {
        "issuer": f"{Config.KC_SERVER_URL}realms/{Config.KC_REALM}",
        "aud": Config.KC_CLIENT_ID,
        "chatbot_user_id": "kakao-user-1",
        "client_key": Config.KC_CLIENT_ID,
        "relay_access_token": "access-token",
        "offline_refresh_token": "refresh-token",
        "expires_in": 300,
        "refresh_expires_in": 3600,
        "ts": int(time.time()),
        "nonce": "nonce-1",
    }
    payload.update(overrides)
    return LoginCallbackReq.model_validate(payload)


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


def test_validate_login_callback_claims_accepts_expected_values() -> None:
    validate_login_callback_claims(make_callback_payload())


def test_validate_login_callback_claims_rejects_invalid_issuer() -> None:
    with pytest.raises(HTTPException, match="invalid_callback_issuer"):
        validate_login_callback_claims(
            make_callback_payload(issuer="https://evil.example/realms/Sandori")
        )


def test_validate_login_callback_claims_rejects_invalid_audience() -> None:
    with pytest.raises(HTTPException, match="invalid_callback_audience"):
        validate_login_callback_claims(make_callback_payload(aud="other-client"))


def test_validate_login_callback_claims_rejects_invalid_client_key() -> None:
    with pytest.raises(HTTPException, match="invalid_callback_client_key"):
        validate_login_callback_claims(make_callback_payload(client_key="other-client"))


def test_verify_timestamp_accepts_within_tolerance() -> None:
    verify_timestamp(int(time.time()))


def test_verify_timestamp_rejects_stale_value() -> None:
    with pytest.raises(HTTPException, match="Timestamp is out of acceptable range"):
        verify_timestamp(int(time.time()) - (Config.NONCE_TTL_SECONDS + 10))


def test_extract_keycloak_sub_returns_expected_sub() -> None:
    assert extract_keycloak_sub(make_access_token()) == "keycloak-sub-1"


def test_extract_keycloak_sub_rejects_expired_token() -> None:
    with pytest.raises(HTTPException, match="expired_access_token"):
        extract_keycloak_sub(make_access_token(exp=int(time.time()) - 10))


def test_extract_keycloak_sub_rejects_invalid_audience() -> None:
    with pytest.raises(HTTPException, match="invalid_access_token_audience"):
        extract_keycloak_sub(make_access_token(azp="other-client"))


def test_extract_keycloak_sub_accepts_audience_fallback_when_azp_is_missing() -> None:
    assert (
        extract_keycloak_sub(make_access_token(azp=None, aud=Config.KC_CLIENT_ID))
        == "keycloak-sub-1"
    )
