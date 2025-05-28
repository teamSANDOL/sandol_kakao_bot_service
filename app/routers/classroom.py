"""빈 강의실 조회 API"""

import asyncio
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from kakao_chatbot import Payload
from kakao_chatbot.input import Param
from kakao_chatbot.response import (
    KakaoResponse,
)
from kakao_chatbot.response.components import (
    SimpleTextComponent,
)

from app.config import logger
from app.schemas.classroom import Classroom, EmptyClassroomInfo
from app.services.classroom_timetable_serivce import (
    search_empty_classroom_by_time,
    search_empty_classroom_now,
)
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
    day_param = payload.action.detail_params.get("day")
    start_time_param = payload.action.detail_params.get("start_time")
    end_time_param = payload.action.detail_params.get("end_time")
    if not day_param or not start_time_param or not end_time_param:
        return JSONResponse(
            KakaoResponse(
                component_list=[
                    SimpleTextComponent(
                        text="빈 강의실 조회에 필요한 파라미터가 부족합니다."
                    )
                ]
            ).get_dict()
        )
    day = day_param.value
    start_time = start_time_param.value
    end_time = end_time_param.value

    logger.info(
        f"시간 기준 빈 강의실 조회 called with day={day},"
        f"start_time={start_time},"
        f"end_time={end_time}"
    )

    empty_classrooms = await search_empty_classroom_by_time(
        client, day, start_time, end_time
    )

    components = make_empty_classroom_components(empty_classrooms)

    return JSONResponse(KakaoResponse(component_list=components).get_dict())


@classroom_router.post(
    "/empty/now",
    openapi_extra=create_openapi_extra(
        utterance="현재 빈 강의실",
    ),
)
async def empty_classroom_now(
    client: Annotated[XUserIDClient, Depends(get_service_xuser_client)],
):
    """현재 빈 강의실을 조회합니다.

    현재 시간에 빈 강의실을 조회하여 리스트 카드 형태로 반환합니다.
    """
    logger.info("현재 빈 강의실 조회 called")

    empty_classrooms = await search_empty_classroom_now(client)

    components = make_empty_classroom_components(empty_classrooms)

    return JSONResponse(KakaoResponse(component_list=components).get_dict())
