"""TUK World(총학생회 제휴 할인 업체) 목록·상세 스킬입니다."""

from typing import Annotated

from fastapi import APIRouter, Depends
from httpx import AsyncClient
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse

from app.services.tuk_world_service import fetch_tuk_world_restaurants
from app.utils.http import get_async_client
from app.utils.kakao import KakaoError, parse_payload
from app.utils.kakao_route import KakaoTimeoutRoute
from app.utils.openapi import create_openapi_extra
from app.utils.tuk_world import (
    make_detail_components,
    make_list_response,
    parse_category,
)

tuk_world_router = APIRouter(prefix="/tuk-world", route_class=KakaoTimeoutRoute)


def _to_int(value: object, default: int = 0) -> int:
    """extra 값을 0 이상의 정수로 바꿉니다. 실패하면 default입니다."""
    try:
        return max(int(str(value)), 0)
    except ValueError:
        return default


@tuk_world_router.post(
    "/list",
    openapi_extra=create_openapi_extra(
        client_extra={"category": "식당", "offset": "0"},
        utterance="TUK월드",
    ),
)
async def tuk_world_list(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
) -> dict[str, object]:
    """제휴 업체 목록을 ListCard Carousel로 반환합니다.

    한 응답에 최대 40곳을 담고, 넘으면 "더 보기" QuickReply로 다음 페이지를 보여줍니다.
    분류(식당·술집·여가)는 client extra 또는 발화로 받습니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 발화 + 버튼/QuickReply 연결
        - "TUK월드", "TUK월드 식당" 등

    - OpenBuilder:
        - 블럭: "TUK월드 목록" (ID는 TUK_WORLD_BLOCK_ID)
        - 스킬: "TUK월드 목록"

    - Params:
        - client_extra:
            category(Optional): 식당 | 술집 | 여가
            offset(Optional): 시작 위치(기본 0)
    ---

    Returns:
        dict: 카카오 스킬 응답
    """
    extra = payload.action.client_extra or {}
    category = parse_category(extra.get("category"), payload.user_request.utterance)
    offset = _to_int(extra.get("offset"))
    restaurants = await fetch_tuk_world_restaurants(client)
    if category:
        restaurants = [r for r in restaurants if r.category == category]
    if offset >= len(restaurants):
        raise KakaoError("등록된 제휴 업체가 없습니다.")
    carousel, quick_replies = make_list_response(restaurants, category, offset)
    response = KakaoResponse(component_list=[carousel])
    response.add_quick_replies(quick_replies)
    return response.get_dict()


@tuk_world_router.post(
    "/detail",
    openapi_extra=create_openapi_extra(client_extra={"id": "1"}),
)
async def tuk_world_detail(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
) -> dict[str, object]:
    """제휴 업체 상세(혜택·이용 조건·주소·지도 버튼)를 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 목록 항목 클릭(블록 연결)

    - OpenBuilder:
        - 블럭: "TUK월드 상세" (ID는 TUK_WORLD_DETAIL_BLOCK_ID)
        - 스킬: "TUK월드 상세"

    - Params:
        - client_extra:
            id: 업체 id
    ---

    Returns:
        dict: 카카오 스킬 응답
    """
    extra = payload.action.client_extra or {}
    target_id = _to_int(extra.get("id"), default=-1)
    restaurants = await fetch_tuk_world_restaurants(client)
    restaurant = next((r for r in restaurants if r.id == target_id), None)
    if restaurant is None:
        raise KakaoError("업체 정보를 찾을 수 없습니다.")
    return KakaoResponse(component_list=make_detail_components(restaurant)).get_dict()
