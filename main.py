"""Sandol의 메인 애플리케이션 파일입니다."""

from contextlib import asynccontextmanager
import traceback
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, status, Depends  # noqa: F401 # pylint: disable=W0611
from fastapi.responses import JSONResponse  # noqa: F401
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import SimpleTextComponent
import uvicorn

from app.routers import meal_router, user_router
from app.config import Config, logger
from app.database import init_db
from app.utils.lifespan import set_service_account
from app.utils import error_message, parse_payload
from app.utils.kakao import KakaoError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI의 lifespan 이벤트 핸들러"""
    logger.info("🚀 서비스 시작: 데이터베이스 init 및 서비스 계정 설정")
    logger.debug(
        "Cofing 정보 로드 %s",
        {
            "dubug": Config.debug,
            "timezone": Config.TIMEZONE,
            "database_url": Config.DATABASE_URL,
            "user_service_url": Config.USER_SERVICE_URL,
        },
    )

    # 애플리케이션 시작 시 데이터베이스 테이블 생성
    await init_db()

    # 서버 시작 시 서비스 계정 설정 실행
    await set_service_account()

    yield  # FastAPI가 실행 중인 동안 유지됨

    # 애플리케이션 종료 시 로그 출력
    logger.info("🛑 서비스 종료: 정리 작업 완료")


app = FastAPI(lifespan=lifespan, root_path="/kakao-bot")
app.include_router(meal_router)
app.include_router(user_router)


@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
    """HTTPException 핸들러입니다.

    예외 발생 시 적절한 응답을 반환합니다.
    예외가 KakaoError인 경우, 해당 예외의 응답을 반환합니다.
    그 외의 경우, 기본적인 에러 메시지를 반환합니다.

    Args:
        request (Request): 요청 객체
        exc (Exception): 발생한 예외

    Returns:
        JSONResponse: 예외에 대한 JSON 응답
    """
    if isinstance(exc, KakaoError):
        return JSONResponse(exc.get_response().get_dict())

    # 예외 처리 시 로그 남기기
    logger.error(
        "Exception occurred: %s\n%s"
        % (exc, "".join(traceback.format_tb(exc.__traceback__)))
    )
    return JSONResponse(KakaoResponse().add_component(error_message(exc)).get_dict())


@app.get("/")
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


if __name__ == "__main__":
    logger.info("Starting Sandol server")
    uvicorn.run("app:app", host="0.0.0.0", port=5600, reload=True)
