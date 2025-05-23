import asyncio
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from kakao_chatbot import Payload
from kakao_chatbot.response import (
    KakaoResponse,
)
from kakao_chatbot.response.components import (
    SimpleTextComponent,
)

from app.config import logger
from app.schemas.notice import Notice
from app.services.notice_service import (
    get_dorm_notice_list,
    get_notice_by_author,
    get_notice_list,
)
from app.utils import create_openapi_extra
from app.utils.auth_client import get_service_xuser_client
from app.utils.http import XUserIDClient
from app.utils.kakao import parse_payload
from app.utils.notice import make_notice_component

notice_router = APIRouter(prefix="/notice")


@notice_router.post(
    "/list",
    openapi_extra=create_openapi_extra(
        detail_params={
            "organization": {
                "origin": "기숙사",
                "value": "생활관",
            },
        },
        utterance="기숙사 공지사항",
    ),
)
async def notice_list(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[XUserIDClient, Depends(get_service_xuser_client)],
):
    """공지사항 목록을 가져옵니다.

    공지사항 목록을 가져와 리스트 카드 형태로 반환합니다.
    공지사항이 없는 경우 "공지사항이 없습니다."라는 메시지를 반환합니다.
    공지사항이 5개 이하인 경우 리스트 카드로 반환하고,
    5개 초과인 경우 Carousel 안에 리스트카드를 넣어 반환합니다.
    최대 20개까지 가져옵니다.
    공지사항도 기숙사  별도로 동일하게 제공합니다.

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
    org = payload.action.params.get("organization", None)
    notice_list: list[Notice] = []
    dorm_notice_list: list[Notice] = []
    if org is None:
        logger.info("전체 공지사항을 요청했습니다.")
        notice_list, dorm_notice_list = await asyncio.gather(
            get_notice_list(client=client, page=1, page_size=20),
            get_dorm_notice_list(client=client, page=1, page_size=20),
        )
    elif org == "생활관":
        logger.info("생활관 공지사항만 요청했습니다.")
        dorm_notice_list = await get_dorm_notice_list(
            client=client, page=1, page_size=20
        )
    else:
        logger.info(f"{org} 조직의 공지사항을 요청했습니다.")
        notice_list, dorm_notice_list = await asyncio.gather(
            get_notice_by_author(client=client, author=org),
            get_notice_by_author(client=client, author=org, is_dormitory=True),
        )

    response = KakaoResponse()

    if notice_list:
        response.add_component(
            make_notice_component(
                notice_list, is_author=(bool(org) and org != "생활관")
            )
        )

    if dorm_notice_list:
        response.add_component(
            make_notice_component(dorm_notice_list, is_dormitory=True)
        )

    if not notice_list and not dorm_notice_list:
        return JSONResponse(
            content=KakaoResponse(
                component_list=[
                    SimpleTextComponent(text="공지사항이 없습니다."),
                ]
            ).get_dict(),
            status_code=200,
        )
    return JSONResponse(
        content=response.get_dict(),
        status_code=200,
    )
