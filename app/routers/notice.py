from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from kakao_chatbot.response import (
    KakaoResponse,
)
from kakao_chatbot.response.components import (
    SimpleTextComponent,
)

from app.config import logger
from app.schemas.notice import Notice
from app.services.notice_service import get_notice_list
from app.utils import create_openapi_extra
from app.utils.auth_client import get_service_xuser_client
from app.utils.http import XUserIDClient
from app.utils.notice import make_notice_response

notice_router = APIRouter(prefix="/notice")


@notice_router.post(
    "/list",
    openapi_extra=create_openapi_extra(
        utterance="공지",
    ),
)
async def notice_list(
    client: Annotated[XUserIDClient, Depends(get_service_xuser_client)],
):
    """공지사항 목록을 가져옵니다.

    공지사항 목록을 가져와 리스트 카드 형태로 반환합니다.
    공지사항이 없는 경우 "공지사항이 없습니다."라는 메시지를 반환합니다.
    공지사항이 5개 이하인 경우 리스트 카드로 반환하고,
    5개 초과인 경우 Carousel 안에 리스트카드를 넣어 반환합니다.
    최대 20개까지 가져옵니다.

    ## 카카오 챗봇  연결 정보
    ---
    - 동작방식: 발화
        - 발화 예시: 공지, 공지사항

    - OpenBuilder:
        - 블럭: "공지사항"
        - 스킬: "공지사항 목록"

    Returns:
        JSONResponse: 공지사항 목록
    """
    logger.info("공지사항 목록을 가져옵니다.")
    notice_list: list[Notice] = await get_notice_list(
        client=client, page=1, page_size=20
    )
    if notice_list:
        return JSONResponse(
            make_notice_response(notice_list).get_dict(), status_code=200
        )
    return JSONResponse(
        content=KakaoResponse(
            component_list=[
                SimpleTextComponent(text="공지사항이 없습니다."),
            ]
        ).get_dict(),
        status_code=200,
    )
