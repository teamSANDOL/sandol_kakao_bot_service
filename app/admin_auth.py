"""Keycloak OIDC 기반 sqladmin 관리자 인증 백엔드.

/admin 경로는 Keycloak 로그인(Authorization Code Flow) 후
KC_ADMIN_ROLE(realm role)을 보유한 계정만 접근할 수 있다.
세션은 Fernet으로 암호화된 쿠키로 관리한다.
"""

import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import jwt
from jwt import InvalidTokenError
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.config import Config, logger
from app.services.auth_service import expected_keycloak_issuer
from app.utils.security import decrypt_token, encrypt_token

ADMIN_SESSION_COOKIE = "sandol_admin_session"
ADMIN_STATE_COOKIE = "sandol_admin_oauth_state"
_STATE_TTL_SECONDS = 600


def admin_oauth_redirect_uri() -> str:
    """Keycloak 클라이언트에 등록된 admin 로그인 콜백 URI."""
    return f"{Config.BASE_URL}/admin-oauth/callback"


def build_admin_login_redirect() -> Response:
    """Keycloak 로그인 페이지로 리다이렉트하는 응답을 생성합니다.

    CSRF 방지를 위한 state 값은 암호화 쿠키에 저장해 콜백에서 검증한다.
    """
    state = secrets.token_urlsafe(32)
    # well-known 조회 없이 표준 엔드포인트 규칙으로 직접 조립한다
    # (익명 요청마다 Keycloak 왕복을 피하기 위함).
    auth_url = (
        f"{expected_keycloak_issuer()}/protocol/openid-connect/auth?"
        + urlencode(
            {
                "client_id": Config.KC_CLIENT_ID,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": admin_oauth_redirect_uri(),
                "state": state,
            }
        )
    )
    response = RedirectResponse(auth_url, status_code=302)
    response.set_cookie(
        ADMIN_STATE_COOKIE,
        encrypt_token(
            json.dumps({"state": state, "exp": int(time.time()) + _STATE_TTL_SECONDS})
        ),
        max_age=_STATE_TTL_SECONDS,
        httponly=True,
        secure=not Config.debug,
        samesite="lax",
        path="/",
    )
    return response


def verify_state_cookie(request: Request, state: str | None) -> bool:
    """콜백으로 돌아온 state 값이 쿠키에 저장한 값과 일치하는지 검증합니다."""
    raw = request.cookies.get(ADMIN_STATE_COOKIE)
    if not raw or not state:
        return False
    try:
        data = json.loads(decrypt_token(raw))
    except (ValueError, RuntimeError):
        return False
    if int(data.get("exp", 0)) <= int(time.time()):
        return False
    return hmac.compare_digest(str(data.get("state", "")), state)


def validate_admin_access_token(access_token: str) -> str:
    """Access Token의 클레임과 관리자 롤을 검증하고 sub를 반환합니다.

    토큰은 confidential client가 Keycloak 토큰 엔드포인트에서 직접 받아온
    것이므로 서명 검증 없이 클레임만 검증한다 (extract_keycloak_sub와 동일한 정책).

    Raises:
        PermissionError: 토큰이 유효하지 않거나 관리자 롤이 없는 경우.
    """
    try:
        payload: dict[str, object] = jwt.decode(
            access_token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except InvalidTokenError as exc:
        raise PermissionError("invalid_access_token") from exc

    exp_claim = payload.get("exp")
    if not isinstance(exp_claim, int) or exp_claim <= int(time.time()):
        raise PermissionError("expired_access_token")

    if payload.get("iss") != expected_keycloak_issuer():
        raise PermissionError("invalid_access_token_issuer")

    realm_access = payload.get("realm_access")
    roles = realm_access.get("roles") if isinstance(realm_access, dict) else None
    if not isinstance(roles, list) or Config.KC_ADMIN_ROLE not in roles:
        raise PermissionError("missing_admin_role")

    keycloak_sub = payload.get("sub")
    if not isinstance(keycloak_sub, str) or not keycloak_sub:
        raise PermissionError("missing_access_token_sub")
    return keycloak_sub


def issue_admin_session_cookie(response: Response, keycloak_sub: str) -> None:
    """관리자 세션 쿠키를 발급하고 state 쿠키를 제거합니다."""
    session_exp = int(time.time()) + Config.ADMIN_SESSION_TTL_SECONDS
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        encrypt_token(json.dumps({"sub": keycloak_sub, "exp": session_exp})),
        max_age=Config.ADMIN_SESSION_TTL_SECONDS,
        httponly=True,
        secure=not Config.debug,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(ADMIN_STATE_COOKIE, path="/")


def read_admin_session(request: Request) -> str | None:
    """세션 쿠키를 검증하고 유효하면 keycloak sub를 반환합니다."""
    raw = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = json.loads(decrypt_token(raw))
    except (ValueError, RuntimeError):
        return None
    if int(data.get("exp", 0)) <= int(time.time()):
        return None
    sub = data.get("sub")
    return sub if isinstance(sub, str) and sub else None


class KeycloakAdminAuth(AuthenticationBackend):
    """Keycloak 로그인 및 관리자 롤을 요구하는 sqladmin 인증 백엔드."""

    def __init__(self) -> None:
        """SessionMiddleware 대신 Fernet 암호화 쿠키를 직접 사용합니다."""
        self.middlewares = []

    async def login(self, request: Request) -> bool:
        """로컬 ID/PW 로그인 폼은 지원하지 않습니다. Keycloak OIDC 로그인만 허용."""
        logger.warning("Admin form login attempted; only Keycloak OIDC login is allowed")
        return False

    async def logout(self, request: Request) -> Response | bool:
        """세션 쿠키를 제거하고 Keycloak 로그아웃 페이지로 보냅니다."""
        end_session_url = (
            f"{Config.KC_SERVER_URL}realms/{Config.KC_REALM}"
            "/protocol/openid-connect/logout"
        )
        response = RedirectResponse(end_session_url, status_code=302)
        response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
        return response

    async def authenticate(self, request: Request) -> Response | bool:
        """유효한 관리자 세션이 없으면 Keycloak 로그인으로 리다이렉트합니다."""
        if read_admin_session(request):
            return True
        return build_admin_login_redirect()
