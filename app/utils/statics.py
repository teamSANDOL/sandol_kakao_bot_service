# ruff: noqa: PLR2004
"""statics router를 위한 유틸리티 함수들입니다."""

import re

from kakao_chatbot.response.components import (
    ListCardComponent,
    CarouselComponent,
    ItemCardComponent,
    SimpleImageComponent,
    SimpleTextComponent,
    Link,
)
from kakao_chatbot.response.base import ParentComponent

from app.config import logger
from app.schemas.statics import (
    OrganizationUnit,
    OrganizationGroup,
)


MAX_SIMPLE_IMAGE_COMPONENTS = 3
CAROUSEL_LIST_CARD_CHUNK_SIZE = 4


def make_org_group_list(
    group: OrganizationGroup,
) -> ListCardComponent | CarouselComponent:
    """조직 그룹 정보를 ListCardComponent 또는 CarouselComponent로 반환합니다.

    조직 그룹의 하위 조직 개수에 따라 ListCard 또는 Carousel을 생성합니다.
    - 5개 이하: 하나의 ListCardComponent에 모든 항목 추가
    - 6개 이상: 4개씩 ListCardComponent로 나누어 CarouselComponent에 추가

    Args:
        group (OrganizationGroup): 조직 그룹 객체
    """
    target_group = group.as_list()
    chunk_size = (
        4  # ListCard에 들어갈 최대 아이템 개수, CarouselComponent 사용 시 4개가 최대
    )

    # 5개 이하일 경우, 하나의 ListCardComponent로 처리
    # PLR2004 규칙을 비활성화합니다.
    # pylint: disable=PLR2004

    if len(target_group) <= 5:
        list_card = ListCardComponent(header=group.name)
        target_list = [list_card]
        chunk_size = 5  # CarouselComponent를 사용하지 않기 때문에 chunk_size를 5로 설정
    else:
        target_list = [
            ListCardComponent(header=group.name)
            for _ in range((len(target_group) + chunk_size - 1) // chunk_size)
        ]  # 4개씩 담을 ListCardComponent들 생성

    # 모든 unit을 순회하면서 적절한 ListCardComponent에 추가
    for idx, unit in enumerate(target_group):
        if isinstance(unit, OrganizationGroup):
            target_list[idx // chunk_size].add_item(
                title=unit.name,
                description="하위 조직 보기",
                action="message",
                message_text=f"{unit.name} 정보",
            )
        else:
            target_list[idx // chunk_size].add_item(
                title=unit.name,
                description="클릭해 정보보기",
                action="block",
                block_id="679ca1348c69ad7d00db038e",
                extra=unit.model_dump(),
            )

    return (
        target_list[0]
        if len(target_group) <= 5
        else CarouselComponent(*target_list)
        )  # 5개 이하일 경우 ListCardComponent 반환, 그 외에는 CarouselComponent 반환


def make_shuttle_info_components(image_urls: list[str]) -> list[ParentComponent]:
    """셔틀버스 이미지 정보를 카카오 응답 컴포넌트로 변환합니다.

    카카오 응답은 최대 3개의 ParentComponent만 포함할 수 있으므로, 이미지가
    4개 이상인 경우 이미지 직접 표시 대신 링크 목록 카드 하나로 폴백합니다.
    """
    if not image_urls:
        return [SimpleTextComponent("셔틀버스 정보가 없습니다.")]

    if len(image_urls) <= MAX_SIMPLE_IMAGE_COMPONENTS:
        return [
            SimpleImageComponent(image_url, "셔틀버스 정보 사진")
            for image_url in image_urls
        ]

    return [make_shuttle_image_link_component(image_urls)]


def make_shuttle_image_link_component(
    image_urls: list[str],
) -> ListCardComponent | CarouselComponent:
    """셔틀버스 이미지 URL 목록을 리스트 카드 또는 캐러셀로 반환합니다."""
    header = "셔틀버스 이미지 바로가기"

    if len(image_urls) <= ListCardComponent(header="").max_items:
        list_card = ListCardComponent(header=header)
        for index, image_url in enumerate(image_urls, start=1):
            list_card.add_item(
                title=f"셔틀버스 정보 {index}",
                description="이미지 링크 열기",
                link=Link(web=image_url),
            )
        return list_card

    carousel = CarouselComponent()
    for start in range(0, len(image_urls), CAROUSEL_LIST_CARD_CHUNK_SIZE):
        list_card = ListCardComponent(header=header, max_items=4)
        for index, image_url in enumerate(
            image_urls[start : start + CAROUSEL_LIST_CARD_CHUNK_SIZE],
            start=start + 1,
        ):
            list_card.add_item(
                title=f"셔틀버스 정보 {index}",
                description="이미지 링크 열기",
                link=Link(web=image_url),
            )
        carousel.add_item(list_card)
    return carousel


def phone_number_format(phone_number: str) -> str:
    """전화번호를 표준 형식으로 변환합니다.

    전화번호를 받아 표준 형식으로 변환하여 반환합니다.
    전화번호가 없는 경우 빈 문자열을 반환합니다.

    Args:
        phone_number (str): 전화번호
    """
    if not phone_number:
        return ""

    # 전화번호에서 숫자만 추출
    phone_number = re.sub(r"[^0-9]", "", phone_number)

    # 전화번호 길이에 따라 형식을 변환
    if len(phone_number) == 9:
        return f"{phone_number[:2]}-{phone_number[2:5]}-{phone_number[5:]}"
    if len(phone_number) == 10:
        return f"{phone_number[:3]}-{phone_number[3:6]}-{phone_number[6:]}"
    if len(phone_number) == 11:
        return f"{phone_number[:3]}-{phone_number[3:7]}-{phone_number[7:]}"
    return phone_number


def make_unit_item(unit: dict | OrganizationUnit) -> ItemCardComponent:
    """조직 단위 정보를 ItemCardComponent로 반환합니다.

    조직 단위 객체를 받아 ItemCardComponent 객체를 생성하여 반환합니다.
    ItemCardComponent 객체는 조직 단위의 이름과 전화번호를 보여줍니다.

    Args:
        unit (OrganizationUnit): 조직 단위 객체
    """
    if isinstance(unit, dict):
        logger.info(f"unit: {unit}")
        unit = OrganizationUnit.model_validate(unit, strict=False)

    item_card = ItemCardComponent(item_list=[], head=unit.name)
    if unit.phone:
        item_card.add_item(
            title="전화번호", description=phone_number_format(unit.phone)
        )
        item_card.add_button(
            label="전화 걸기", action="phone", phone_number=unit.phone)

    if unit.url:
        item_card.add_item(title="홈페이지", description=unit.url)
        item_card.add_button(
            label="홈페이지 방문", action="webLink", web_link_url=unit.url
        )

    if not unit.phone and not unit.url:
        item_card.add_item(
            title="정보 없음", description="전화번호 및 홈페이지 정보가 없습니다."
        )
    return item_card
