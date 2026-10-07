"""카카오 스킬의 의존성과 endpoint 실행에 시간 예산을 적용한다."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import SimpleTextComponent

from app.config import Config, logger


class KakaoTimeoutRoute(APIRoute):
    """내부 route를 제외한 카카오 스킬 처리 시간을 제한한다."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """FastAPI 의존성 처리와 endpoint 실행을 함께 감싼다."""
        original_handler = super().get_route_handler()
        if "internal" in (self.tags or []):
            return original_handler

        async def handler(request: Request) -> Response:
            timeout = asyncio.timeout(Config.KAKAO_REQUEST_TIMEOUT_SECONDS)
            try:
                async with timeout:
                    return await original_handler(request)
            except TimeoutError:
                if not timeout.expired():
                    raise
                logger.warning("Kakao request timeout: route=%s", self.path)
                response = KakaoResponse().add_component(
                    SimpleTextComponent(
                        "처리 시간이 초과되어 결과를 확인하지 못했습니다. "
                        "등록 요청이었다면 등록 상태를 먼저 확인해주세요."
                    )
                )
                return JSONResponse(response.get_dict(), status_code=200)

        return handler
