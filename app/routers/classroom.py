"""빈 강의실 조회 API"""

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
from app.schemas.classroom import Classroom, EmptyClassroomInfo
from app.services.classroom_timetable_serivce import search_empty_classroom_by_time
from app.utils import create_openapi_extra
from app.utils.auth_client import get_service_xuser_client
from app.utils.http import XUserIDClient
from app.utils.kakao import parse_payload
from app.utils.classroom import make_empty_classroom_components

classroom_router = APIRouter(prefix="/classroom")

@classroom_router.post(
    "/empty/time",
    openapi_extra=create_openapi_extra(
        detail_params={
            "day": {
                "origin": "월",
                "value": "월요일",
            },
            "start_time": {
                "origin": "09:00",
                "value": "09:00",
            },
            "end_time": {
                "origin": "10:00",
                "value": "10:00",
            },
        },
    ),
)
async def empty_classroom_by_time(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[XUserIDClient, Depends(get_service_xuser_client)],
):
    """빈 강의실을 조회합니다.

    빈 강의실을 조회하여 리스트 카드 형태로 반환합니다.
    """
    day = payload.action.detail_params.get("day", "월요일")
    start_time = payload.action.detail_params.get("start_time", "09:00")
    end_time = payload.action.detail_params.get("end_time", "10:00")

    logger.info(
        f"시간 기준 빈 강의실 조회 called with day={day}, start_time={start_time}, end_time={end_time}"
    )

    empty_classrooms = await search_empty_classroom_by_time(client, day, start_time, end_time)

    components = make_empty_classroom_components(empty_classrooms)

    return JSONResponse(KakaoResponse(
        component_list=components
    ).get_dict()
    )
