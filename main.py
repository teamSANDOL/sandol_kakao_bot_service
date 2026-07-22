"""Sandol의 메인 애플리케이션 파일입니다."""

from contextlib import asynccontextmanager
import traceback
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, status, Depends  # noqa: F401 # pylint: disable=W0611
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: F401
from fastapi.routing import APIRoute
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import SimpleTextComponent
from keycloak.exceptions import KeycloakError
from sqladmin import Admin
import uvicorn

from app.admin_auth import (
    KeycloakAdminAuth,
    admin_oauth_redirect_uri,
    issue_admin_session_cookie,
    read_code_verifier,
    validate_admin_access_token,
    verify_state_cookie,
)
from app.models.admin import UserAdmin
from app.services.auth_service import get_keycloak_client
from app.routers import (
    meal_router,
    user_router,
    statics_router,
    notice_router,
    classroom_router,
)
from app.config import Config, logger
from app.database import init_db, async_engine
from app.utils import error_message, parse_payload
from app.utils.kakao import (
    KakaoError,
    LoginRequiredError,
    NotAuthenticated,
    UserIdentityConflictError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI의 lifespan 이벤트 핸들러."""
    logger.info("🚀 서비스 시작: 데이터베이스 init 및 서비스 계정 설정")
    logger.debug(
        "Cofing 정보 로드 %s",
        {
            "debug": Config.debug,
            "timezone": Config.TIMEZONE,
            "database_url": Config.DATABASE_URL,
        },
    )

    # 애플리케이션 시작 시 데이터베이스 테이블 생성
    if Config.debug:
        logger.debug("Debug 모드: 데이터베이스 initialization 시작")
        await init_db()

    yield  # FastAPI가 실행 중인 동안 유지됨

    # 애플리케이션 종료 시 로그 출력
    logger.info("🛑 서비스 종료: 정리 작업 완료")


app = FastAPI(lifespan=lifespan, root_path="/kakao-bot")
app.include_router(meal_router)
app.include_router(user_router)
app.include_router(statics_router)
app.include_router(notice_router)
app.include_router(classroom_router)

# Admin 패널은 Keycloak OIDC 인증(KC_ADMIN_ROLE 롤 필수)이 가능할 때만 마운트한다.
# 인증을 구성할 수 없으면 마운트하지 않아 외부에 노출되지 않는다 (fail-closed).
if Config.ADMIN_PANEL_ENABLED and Config.KC_CLIENT_SECRET:
    admin = Admin(
        app=app,
        engine=async_engine,
        authentication_backend=KeycloakAdminAuth(),
    )
    admin.add_view(UserAdmin)
else:
    logger.warning(
        "Admin panel is NOT mounted (%s)",
        "ADMIN_PANEL_ENABLED=false"
        if not Config.ADMIN_PANEL_ENABLED
        else "KC_CLIENT_SECRET is not configured",
    )


@app.get("/admin-oauth/callback", tags=["internal"], include_in_schema=False)
async def admin_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Keycloak 로그인 후 admin 세션 쿠키를 발급하는 OIDC 콜백 엔드포인트입니다."""
    if not (Config.ADMIN_PANEL_ENABLED and Config.KC_CLIENT_SECRET):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if error:
        logger.warning("Admin OAuth callback returned error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_login_failed"
        )
    if not code or not verify_state_cookie(request, state):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_oauth_state"
        )

    code_verifier = read_code_verifier(request)
    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_code_verifier"
        )

    try:
        token_data = get_keycloak_client().token(
            grant_type="authorization_code",
            code=code,
            redirect_uri=admin_oauth_redirect_uri(),
            code_verifier=code_verifier,
        )
    except KeycloakError as exc:
        logger.warning("Admin OAuth code exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin_token_exchange_failed",
        ) from exc

    try:
        keycloak_sub = validate_admin_access_token(str(token_data["access_token"]))
    except PermissionError as exc:
        logger.warning("Admin login rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin_role_required"
        ) from exc

    logger.info("Admin login succeeded for keycloak_sub=%s", keycloak_sub)
    response = RedirectResponse(f"{Config.BASE_URL}/admin", status_code=302)
    issue_admin_session_cookie(response, keycloak_sub)
    return response


def is_internal_route(request: Request) -> bool:
    """요청이 internal 라우트에 대한 것인지 확인하는 유틸리티 함수입니다."""
    route = request.scope.get("route")
    return isinstance(route, APIRoute) and "internal" in set(route.tags or [])


def _build_internal_error_response(exc: Exception | HTTPException) -> JSONResponse:
    """Internal 라우트용 예외 응답을 생성합니다."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )


def _build_kakao_exception_response(
    exc: KakaoError | LoginRequiredError | NotAuthenticated | UserIdentityConflictError,
) -> JSONResponse:
    """Kakao 제어 흐름 예외를 200 응답으로 변환합니다."""
    return JSONResponse(exc.get_response().get_dict())


@app.exception_handler(KakaoError)
async def kakao_error_handler(request: Request, exc: KakaoError) -> JSONResponse:
    """KakaoError를 사용자 응답으로 변환합니다."""
    if is_internal_route(request):
        return _build_internal_error_response(exc)
    return _build_kakao_exception_response(exc)


@app.exception_handler(LoginRequiredError)
async def login_required_error_handler(
    request: Request,
    exc: LoginRequiredError,
) -> JSONResponse:
    """LoginRequiredError를 사용자 응답으로 변환합니다."""
    if is_internal_route(request):
        return _build_internal_error_response(exc)
    return _build_kakao_exception_response(exc)


@app.exception_handler(NotAuthenticated)
async def not_authenticated_error_handler(
    request: Request,
    exc: NotAuthenticated,
) -> JSONResponse:
    """NotAuthenticated를 사용자 응답으로 변환합니다."""
    if is_internal_route(request):
        return _build_internal_error_response(exc)
    return _build_kakao_exception_response(exc)


@app.exception_handler(UserIdentityConflictError)
async def user_identity_conflict_error_handler(
    request: Request,
    exc: UserIdentityConflictError,
) -> JSONResponse:
    """UserIdentityConflictError를 사용자 응답으로 변환합니다."""
    if is_internal_route(request):
        return _build_internal_error_response(exc)
    return _build_kakao_exception_response(exc)


@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception | HTTPException):
    """일반 예외를 적절한 응답으로 변환합니다.

    예외 발생 시 적절한 응답을 반환합니다.
    내부 라우트는 HTTP 상태코드를 유지하고,
    그 외의 경우 기본적인 Kakao 에러 메시지를 반환합니다.

    Args:
        request (Request): 요청 객체
        exc (Exception): 발생한 예외

    Returns:
        JSONResponse: 예외에 대한 JSON 응답
    """
    if is_internal_route(request):
        return _build_internal_error_response(exc)

    # 예외 처리 시 로그 남기기
    logger.error(
        "Exception occurred: %s\n%s"
        % (exc, "".join(traceback.format_tb(exc.__traceback__)))
    )
    return JSONResponse(KakaoResponse().add_component(error_message(exc)).get_dict())


@app.get("/", tags=["internal"])
async def root():
    """루트 엔드포인트입니다."""
    logger.info("Root endpoint accessed")
    return {"test": "Hello Sandol"}


@app.post("/get_id")
async def get_id(payload: Annotated[Payload, Depends(parse_payload)]):
    """사용자의 ID를 반환하는 엔드포인트입니다."""
    logger.info(
        "Get ID endpoint accessed\nkakao_id: %s\napp_user_id: %s\nplusfriend_user_key: %s",
        payload.user_request.user.id,
        payload.user_request.user.properties.app_user_id,
        payload.user_request.user.properties.plusfriend_user_key,
    )
    logger.debug(f"User ID: {payload.user_id or 'No ID'}")
    response = KakaoResponse()
    response.add_component(SimpleTextComponent(payload.user_id or "No ID"))
    return JSONResponse(response.get_dict())


@app.get("/health", tags=["internal"])
async def health_check():
    """Health check 엔드포인트입니다."""
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    logger.info("Starting Sandol server")
    uvicorn.run("app:app", host="0.0.0.0", port=5600, reload=True)
