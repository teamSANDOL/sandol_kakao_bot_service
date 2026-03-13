"""빈 강의실 조회 API입니다."""

import re
from typing import Annotated
from fastapi import APIRouter, Depends
from httpx import AsyncClient
from kakao_chatbot import Payload
from kakao_chatbot.response import (
    KakaoResponse,
)
from kakao_chatbot.response.components import (
    SimpleTextComponent,
)

from app.config import logger
from app.services.classroom_timetable_service import (
    search_empty_classroom_by_time,
    search_empty_classroom_by_period,
    search_empty_classroom_now,
)
from app.utils import create_openapi_extra
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload, extract_text_value
from app.utils.classroom import (
    make_empty_classroom_components,
    make_empty_classroom_detail_component,
    parse_day_name,
)

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
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """빈 강의실을 시간 기준으로 조회합니다.

    빈 강의실을 조회하여 리스트 카드 형태로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "시간 기준 강의실 찾기"
        - 스킬: "시간 기준 강의실 찾기"

    - Params:
        - detail_params:
            - day: 요일 (예: "월요일", "화요일" 등)
            - start_time: 시작 시간 (예: "09:00")
            - end_time: 종료 시간 (예: "10:00")
    ---

    Returns:
        JSONResponse: 빈 강의실 정보가 담긴 JSON 응답
    """
    day_param = payload.action.detail_params.get("day")
    start_time_param = payload.action.detail_params.get("start_time")
    end_time_param = payload.action.detail_params.get("end_time")
    if not day_param or not start_time_param or not end_time_param:
        return KakaoResponse(
            component_list=[
                SimpleTextComponent(
                    text="빈 강의실 조회에 필요한 파라미터가 부족합니다."
                )
            ]
        ).get_dict()
    day = parse_day_name(day_param.value)
    start_time = extract_text_value(start_time_param.value)
    end_time = extract_text_value(end_time_param.value)
    if day is None or start_time is None or end_time is None:
        return KakaoResponse(
            component_list=[
                SimpleTextComponent(
                    text="빈 강의실 조회 파라미터 형식이 올바르지 않습니다."
                )
            ]
        ).get_dict()

    logger.info(
        f"시간 기준 빈 강의실 조회 called with day={day},"
        f"start_time={start_time},"
        f"end_time={end_time}"
    )

    empty_classrooms = await search_empty_classroom_by_time(
        client, day, start_time, end_time
    )

    components = make_empty_classroom_components(empty_classrooms)

    return KakaoResponse(component_list=components).get_dict()


@classroom_router.post(
    "/empty/now",
    openapi_extra=create_openapi_extra(
        utterance="현재 빈 강의실",
    ),
)
async def empty_classroom_now(
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """현재 빈 강의실을 조회합니다.

    현재 시간에 빈 강의실을 조회하여 리스트 카드 형태로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 발화, 버튼 연결
        - 현재 비어있는 교실
        - 지금 비어있는 강의실

    - OpenBuilder:
        - 블럭: "지금 빈 강의실"
        - 스킬: "지금 빈 강의실"
    ---

    Returns:
        JSONResponse: 현재 빈 강의실 정보가 담긴 JSON 응답
    """
    logger.info("현재 빈 강의실 조회 called")

    empty_classrooms = await search_empty_classroom_now(client)

    components = make_empty_classroom_components(empty_classrooms)

    return KakaoResponse(component_list=components).get_dict()


@classroom_router.post(
    "/empty/period",
    openapi_extra=create_openapi_extra(
        detail_params={
            "day": {
                "origin": "월",
                "value": "월요일",
            },
            "start_period": {
                "origin": "1교시",
                "value": 1,
            },
            "end_period": {
                "origin": "2교시",
                "value": 2,
            },
        },
    ),
)
async def empty_classroom_by_period(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """빈 강의실을 교시 기준으로 조회합니다.

    빈 강의실을 조회하여 리스트 카드 형태로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "교시 기준 강의실 찾기"
        - 스킬: "교시 기준 강의실 찾기"

    - Params:
        - detail_params:
            - day: 요일 (예: "월요일", "화요일" 등)
            - start_period: 시작 교시 (예: "1교시")
            - end_period: 종료 교시 (예: "2교시")
    ---

    Returns:
        JSONResponse: 빈 강의실 정보가 담긴 JSON 응답
    """
    day_param = payload.action.detail_params.get("day")
    start_period_param = payload.action.detail_params.get("start_period")
    end_period_param = payload.action.detail_params.get("end_period")
    if not day_param or not start_period_param or not end_period_param:
        return KakaoResponse(
            component_list=[
                SimpleTextComponent(
                    text="빈 강의실 조회에 필요한 파라미터가 부족합니다."
                )
            ]
        ).get_dict()
    day = parse_day_name(day_param.value)
    start_period_raw = extract_text_value(start_period_param.value)
    end_period_raw = extract_text_value(end_period_param.value)
    if day is None or start_period_raw is None or end_period_raw is None:
        return KakaoResponse(
            component_list=[
                SimpleTextComponent(
                    text="빈 강의실 조회 파라미터 형식이 올바르지 않습니다."
                )
            ]
        ).get_dict()

    start_period_str = start_period_raw.rstrip("교시")
    end_period_str = end_period_raw.rstrip("교시")

    start_period_match = re.match(r"\d+", start_period_str)
    end_period_match = re.match(r"\d+", end_period_str)

    if not start_period_match or not end_period_match:
        return KakaoResponse(
            component_list=[
                SimpleTextComponent(text="교시 파라미터 형식이 올바르지 않습니다.")
            ]
        ).get_dict()

    start_period: int = int(start_period_match.group())
    end_period: int = int(end_period_match.group())
    logger.info(
        f"교시 기준 빈 강의실 조회 called with day={day},"
        f"start_period={start_period},"
        f"end_period={end_period}"
    )
    empty_classrooms = await search_empty_classroom_by_period(
        client, day, start_period, end_period
    )
    components = make_empty_classroom_components(empty_classrooms)
    return KakaoResponse(component_list=components).get_dict()


@classroom_router.post(
    "/empty/detail",
    openapi_extra=create_openapi_extra(
        client_extra={
            "empty_classroom_info": {
                "building": "A동",
                "empty_classrooms": [
                    {"room_name": "101호"},
                    {"room_name": "102호"},
                ],
                "empty_classrooms_by_floor": {
                    1: [{"room_name": "101호"}, {"room_name": "102호"}],
                },
            }
        },
    ),
)
async def empty_classroom_detail(
    payload: Annotated[Payload, Depends(parse_payload)],
) -> dict:
    """빈 강의실 상세 정보를 조회합니다.

    빈 강의실 상세 정보를 조회하여 캐로셀 형태로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "빈 강의실 상세 정보"
        - 스킬: "빈 강의실 상세 정보"

    - Params:
        - client_extra:
            - empty_classroom_info: 빈 강의실 정보 (예시로 제공됨)
    ---

    Returns:
        JSONResponse: 빈 강의실 상세 정보가 담긴 JSON 응답
    """
    logger.info("빈 강의실 상세 정보 조회 called")
    info = payload.action.client_extra.get("empty_classroom_info")
    if info is None:
        return KakaoResponse(
            component_list=[SimpleTextComponent(text="상세 정보를 찾을 수 없습니다.")]
        ).get_dict()

    carousel = make_empty_classroom_detail_component(info=info)
    return KakaoResponse(component_list=[carousel]).get_dict()
