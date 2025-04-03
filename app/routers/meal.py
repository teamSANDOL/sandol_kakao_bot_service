"""학식 관련 API 파일입니다.

학식 관련 API가 작성되어 있습니다.
학식 보기, 등록, 삭제 등의 기능을 담당합니다.
"""
from typing import Annotated
from datetime import datetime, timedelta

from fastapi import Depends, APIRouter
from fastapi.responses import JSONResponse

from kakao_chatbot import Payload

from app.config import Config, logger
from app.schemas.meals import MealResponse
from app.models.user import User
from app.services.meal_service import fetch_latest_meals
from app.utils.auth_client import get_xuser_client_by_payload
from app.utils.db import get_current_user
from app.utils.http import XUserIDClient
from app.utils import create_openapi_extra
from app.utils.kakao import parse_payload

meal_api = APIRouter(prefix="/meal")


@meal_api.post(
    "/view",
    openapi_extra=create_openapi_extra(
        detail_params={
            "Cafeteria": {
                "origin": "미가",
                "value": "미가식당",
            },
        },
        utterance="학식 미가",
    ),
)
async def meal_view(
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
) -> JSONResponse:
    """식단 정보를 Carousel TextCard 형태로 반환합니다.

    등록된 식당 정보를 불러와 어제 7시 이후 등록된 식당 정보를 먼저 배치합니다.
    그 후 어제 7시 이전 등록된 식당 정보를 배치합니다.
    이를 통해 어제 7시 이후 등록된 식당 정보가 먼저 보이도록 합니다.
    이를 토대로 점심과 저녁 메뉴를 담은 Carousel을 생성합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 발화
        - "학식"
        - "학식 <식당>"
        - "메뉴 <식당>"
        - 등

    - OpenBuilder:
        - 블럭: "학식 보기"
        - 스킬: "학식 보기"

    - Params:
        - detail_params:
            - Cafeteria(식당): 식당 이름(Optional)
    ---

    Returns:
        str: 식단 정보를 반환합니다.
    """
    logger.info("식단 정보 조회 요청 수신: user_id=%s", payload.user_request.user.id)
    # payload에서 Cafeteria 값 추출
    assert payload.action.detail_params is not None
    cafeteria = payload.action.detail_params.get("Cafeteria")  # 학식 이름
    target_cafeteria = getattr(cafeteria, "value", None)

    # 식단 정보를 가져옵니다.
    meal_list = await fetch_latest_meals(client)

    # cafeteria 값이 있을 경우 해당 식당 정보로 필터링
    if target_cafeteria:
        logger.debug("식단 정보 필터링: target_cafeteria=%s", target_cafeteria)
        meals = list(filter(lambda x: x.restaurant_name == target_cafeteria, meal_list))
    else:
        meals = meal_list

    # 어제 7시를 기준으로 식당 정보를 필터링
    standard_time = datetime.now(tz=Config.TZ) - timedelta(days=1)
    standard_time = standard_time.replace(hour=19, minute=0, second=0, microsecond=0)

    af_standard: list[MealResponse] = []
    bf_standard: list[MealResponse] = []
    logger.debug("식당 정보 정렬 시작: user_id=%s", user.id)
    for r in meals:
        if r.updated_at < standard_time:
            logger.debug("식당 정보 정렬: %s | 어제 7시 이전 등록", r.name)
            bf_standard.append(r)
        else:
            logger.debug("식당 정보 정렬: %s | 어제 7시 이후 등록", r.name)
            af_standard.append(r)

    bf_standard.sort(key=lambda x: x.updated_at)
    af_standard.sort(key=lambda x: x.updated_at)

    # 어제 7시 이후 등록된 식당 정보를 먼저 배치
    restaurants = af_standard + bf_standard

    # 점심과 저녁 메뉴를 담은 Carousel 생성
    lunch_carousel, dinner_carousel = make_meal_cards(restaurants)

    response = KakaoResponse()

    # 점심과 저녁 메뉴 Carousel을 SkillList에 추가
    # 비어있는 Carousel을 추가하지 않음
    if not lunch_carousel.is_empty:
        response.add_component(lunch_carousel)
    if not dinner_carousel.is_empty:
        response.add_component(dinner_carousel)
    if not response.component_list:
        logger.debug("식단 정보가 없습니다: user_id=%s", payload.user_request.user.id)
        response.add_component(SimpleTextComponent("식단 정보가 없습니다."))

    # 퀵리플라이 추가
    # 현재 선택된 식단을 제외한 다른 식당을 퀵리플라이로 추가
    if target_cafeteria:
        response.add_quick_reply(
            label="모두 보기",
            action="message",
            message_text="학식",
        )

    for rest in cafeteria_list:
        if rest.name != target_cafeteria:
            response.add_quick_reply(
                label=rest.name,
                action="message",
                message_text=f"학식 {rest.name}",
            )

    logger.info("식단 정보 조회 완료: user_id=%s", payload.user_request.user.id)
    return JSONResponse(response.get_dict())
