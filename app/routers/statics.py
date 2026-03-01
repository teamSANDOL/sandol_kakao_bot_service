"""학교 조직 정보 및 셔틀버스 이미지 링크를 가져오는 서비스 모듈입니다.

자주 변경되지 않는 정적 정보를 제공하는 API를 구현합니다.
"""

from typing import Annotated

from fastapi import Depends
from fastapi import APIRouter
from httpx import AsyncClient
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import (
    SimpleTextComponent,
    SimpleImageComponent,
)

from app.schemas.statics import OrganizationGroup
from app.services.static_service import (
    fetch_shuttle_img_inks,
    search_organization,
)
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload, extract_text_value
from app.utils.openapi import create_openapi_extra
from app.utils.statics import (
    make_org_group_list,
    make_unit_item,
)


statics_router = APIRouter(prefix="/statics")


@statics_router.post(
    "/info",
    openapi_extra=create_openapi_extra(
        detail_params={
            "organization": {
                "origin": "컴공",
                "value": "컴퓨터공학부",
            },
        },
        utterance="컴공 정보",
    ),
)
async def info(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """학교 조직정보를 반환합니다.

    조직이 하위 조직을 갖는 경우 조직의 리스트를,
    하위 조직이 없는 경우 조직의 정보를 반환합니다.

    ## 카카오 챗봇  연결 정보
    ---
    - 동작방식: 발화

    - OpenBuilder:
        - 블럭: "정보 검색"
        - 스킬: "정보 검색"

    - Params:
        - detail_params:
            organization(조직): 컴퓨터공학부
    ---

    Returns:
        JSONResponse: 학교 조직 정보
    """
    org_raw = payload.action.params.get("organization", None)
    org = extract_text_value(org_raw) if org_raw is not None else None
    if org is None:
        org = "대표연락처"
    unit = await search_organization(client, org)

    if unit is None:
        return KakaoResponse(
            component_list=[SimpleTextComponent("해당 조직을 찾을 수 없습니다.")]
        ).get_dict()

    if isinstance(unit, OrganizationGroup):
        return KakaoResponse(component_list=[make_org_group_list(unit)]).get_dict()
    return KakaoResponse(component_list=[make_unit_item(unit)]).get_dict()


@statics_router.post(
    "/unit_info",
    openapi_extra=create_openapi_extra(
        client_extra={
            "name": "컴퓨터공학부",
            "phone": "03180410510",
        }
    ),
)
async def unit_info(payload: Annotated[Payload, Depends(parse_payload)]):
    """학교 조직 정보를 반환합니다.

    Client Extra에 있는 정보를 기반으로 학교 조직 정보를 반환합니다.

    ## 카카오 챗봇  연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "조직 정보"
        - 스킬: "조직 정보"

    - Params:
        - client_extra:
            name: 컴퓨터공학부
            phone: 03180410510
    ---

    Returns:
        JSONResponse: 학교 조직 정보
    """
    return KakaoResponse(
        component_list=[make_unit_item(payload.action.client_extra)]
    ).get_dict()


@statics_router.post(
    "/shuttle_info",
    openapi_extra=create_openapi_extra(
        utterance="셔틀버스",
    ),
)
async def shuttle_info(
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """셔틀버스 정보를 반환합니다.

    ## 카카오 챗봇  연결 정보
    ---
    - 동작방식: 발화

    - OpenBuilder:
        - 블럭: "셔틀버스 정보"
        - 스킬: "셔틀버스 정보"
    ---

    Returns:
        JSONResponse: 셔틀버스 정보
    """
    shuttle_images = await fetch_shuttle_img_inks(client)
    shuttle_images.reverse()

    components = [
        SimpleImageComponent(image, "셔틀버스 정보 사진") for image in shuttle_images
    ]
    response = KakaoResponse()
    for component in components:
        response.add_component(component)
    return response.get_dict()
