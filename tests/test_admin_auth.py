"""Admin 패널 Keycloak 인증 백엔드 테스트."""

import base64
import hashlib
import json
import time

import jwt
import pytest
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.admin_auth import (
    ADMIN_SESSION_COOKIE,
    ADMIN_STATE_COOKIE,
    KeycloakAdminAuth,
    build_admin_login_redirect,
    issue_admin_session_cookie,
    read_admin_session,
    read_code_verifier,
    validate_admin_access_token,
    verify_state_cookie,
)
from app.config import Config
from app.services.auth_service import expected_keycloak_issuer
from app.utils.security import encrypt_token


def _make_request(cookies: dict[str, str] | None = None) -> Request:
    cookie_header = "; ".join(f"{k}={v}" for k, v in (cookies or {}).items())
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)


def _make_access_token(
    *,
    roles: list[str] | None = None,
    exp_offset: int = 300,
    iss: str | None = None,
    sub: str = "admin-sub",
) -> str:
    payload = {
        "sub": sub,
        "exp": int(time.time()) + exp_offset,
        "iss": iss if iss is not None else expected_keycloak_issuer(),
        "realm_access": {"roles": roles if roles is not None else ["global_admin"]},
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _extract_cookie(response: Response, name: str) -> str | None:
    for header_value in response.headers.getlist("set-cookie"):
        if header_value.startswith(f"{name}="):
            return header_value.split(";", 1)[0].split("=", 1)[1]
    return None


class TestValidateAdminAccessToken:
    def test_valid_admin_token_returns_sub(self):
        token = _make_access_token()
        assert validate_admin_access_token(token) == "admin-sub"

    def test_missing_admin_role_rejected(self):
        token = _make_access_token(roles=["offline_access"])
        with pytest.raises(PermissionError, match="missing_admin_role"):
            validate_admin_access_token(token)

    def test_expired_token_rejected(self):
        token = _make_access_token(exp_offset=-10)
        with pytest.raises(PermissionError, match="expired_access_token"):
            validate_admin_access_token(token)

    def test_wrong_issuer_rejected(self):
        token = _make_access_token(iss="https://evil.example.com/realms/Sandori")
        with pytest.raises(PermissionError, match="invalid_access_token_issuer"):
            validate_admin_access_token(token)

    def test_garbage_token_rejected(self):
        with pytest.raises(PermissionError):
            validate_admin_access_token("not-a-jwt")


class TestAdminSessionCookie:
    def test_issue_and_read_roundtrip(self):
        response = Response()
        issue_admin_session_cookie(response, "admin-sub")
        cookie = _extract_cookie(response, ADMIN_SESSION_COOKIE)
        assert cookie is not None

        request = _make_request({ADMIN_SESSION_COOKIE: cookie})
        assert read_admin_session(request) == "admin-sub"

    def test_expired_session_rejected(self):
        cookie = encrypt_token(
            json.dumps({"sub": "admin-sub", "exp": int(time.time()) - 1})
        )
        request = _make_request({ADMIN_SESSION_COOKIE: cookie})
        assert read_admin_session(request) is None

    def test_tampered_session_rejected(self):
        request = _make_request({ADMIN_SESSION_COOKIE: "tampered-value"})
        assert read_admin_session(request) is None


class TestStateCookie:
    def test_state_roundtrip(self):
        response = build_admin_login_redirect()
        assert isinstance(response, RedirectResponse)
        assert "protocol/openid-connect/auth" in response.headers["location"]

        state_cookie = _extract_cookie(response, ADMIN_STATE_COOKIE)
        assert state_cookie is not None

        # 리다이렉트 URL의 state 파라미터와 쿠키가 일치해야 검증 통과
        location = response.headers["location"]
        state_value = location.split("state=", 1)[1].split("&", 1)[0]
        request = _make_request({ADMIN_STATE_COOKIE: state_cookie})
        assert verify_state_cookie(request, state_value) is True
        assert verify_state_cookie(request, "wrong-state") is False

    def test_missing_state_rejected(self):
        request = _make_request()
        assert verify_state_cookie(request, "anything") is False

    def test_login_redirect_includes_pkce_challenge(self):
        response = build_admin_login_redirect()
        location = response.headers["location"]
        assert "code_challenge_method=S256" in location

        code_challenge = location.split("code_challenge=", 1)[1].split("&", 1)[0]

        state_cookie = _extract_cookie(response, ADMIN_STATE_COOKIE)
        request = _make_request({ADMIN_STATE_COOKIE: state_cookie})
        code_verifier = read_code_verifier(request)
        assert code_verifier is not None

        # 콜백에서 쓸 code_verifier가 로그인 요청에 실은 code_challenge와 대응해야 한다
        expected_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("ascii")).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )
        assert code_challenge == expected_challenge

    def test_code_verifier_missing_without_cookie(self):
        request = _make_request()
        assert read_code_verifier(request) is None


class TestKeycloakAdminAuth:
    @pytest.mark.asyncio
    async def test_authenticate_without_session_redirects_to_keycloak(self):
        backend = KeycloakAdminAuth()
        result = await backend.authenticate(_make_request())
        assert isinstance(result, RedirectResponse)
        assert "protocol/openid-connect/auth" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_authenticate_with_valid_session_allows(self):
        response = Response()
        issue_admin_session_cookie(response, "admin-sub")
        cookie = _extract_cookie(response, ADMIN_SESSION_COOKIE)

        backend = KeycloakAdminAuth()
        result = await backend.authenticate(
            _make_request({ADMIN_SESSION_COOKIE: cookie})
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_form_login_disabled(self):
        backend = KeycloakAdminAuth()
        assert await backend.login(_make_request()) is False


def test_admin_role_default_config():
    assert Config.KC_ADMIN_ROLE == "global_admin"
