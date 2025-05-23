"""조회된 공지사항을 카카오톡 챗봇의 카드 형식으로 변환하는 유틸리티 모듈입니다.

카카오톡 챗봇에서 공지사항을 보여주기 위해서는 리스트 카드 또는 캐러셀 형식으로 변환해야 합니다.
"""
from kakao_chatbot.response.components import (
    ListCardComponent,
    ListItem,
    Link,
    CarouselComponent,
    SimpleTextComponent,
)

from app.schemas.notice import Notice
from app.config import logger


def notice_to_list_item(notice: Notice) -> ListItem:
    """공지사항을 리스트 아이템으로 변환합니다.

    아이템의 제목은 공지사항의 제목으로 설정하고,
    설명은 작성자와 작성일시로 설정합니다.
    공지사항의 URL을 링크로 설정합니다.

    Args:
        notice (Notice): 공지사항 객체

    Returns:
        ListItem: 카카오톡 리스트 아이템
    """
    formatted_time = notice.create_at.strftime("%-m월 %-d일 %-H시 %-M분")
    description = f"{notice.author} | {formatted_time}"
    return ListItem(
        title=notice.title,
        description=description,
        link=Link(
            web=notice.url,
        ),
    )


def make_notice_component(
    notice_list: list[Notice],
    is_author: bool = False,
    is_dormitory: bool = False,
) -> SimpleTextComponent | ListCardComponent | CarouselComponent:
    """공지사항 목록을 리스트 카드 또는 캐러셀로 변환합니다.

    공지사항이 5개 이하인 경우 리스트 카드로 반환하고,
    5개 초과인 경우 캐러셀 안에 리스트카드를 넣어 반환합니다.
    공지사항이 없는 경우 "공지사항이 없습니다."라는 메시지를 반환합니다.
    작성자 조회 시 작성자 이름을 헤더로 설정합니다.
    기숙사 조회 시 "생활관 공지사항"으로 설정합니다.

    Args:
        notice_list (list[Notice]): 공지사항 목록
        is_author (bool): 작성자 조회 여부
        is_dormitory (bool): 기숙사 조회 여부
    Returns:
        SimpleTextComponent | ListCardComponent | CarouselComponent: 공지사항 목록
    """
    if is_author and is_dormitory:
        logger.warning("is_author and is_dormitory both True")
    if is_author:
        author = notice_list[0].author
        header = f"{author} 공지사항"
    elif is_dormitory:
        header = "생활관 공지사항"
    else:
        header = "공지사항"

    if not notice_list:
        return SimpleTextComponent(
                text=f"{header}을 찾을 수 없습니다.",
            )

    if len(notice_list) < ListCardComponent(header="").max_items:
        return ListCardComponent(
            header=header,
            items=[notice_to_list_item(notice) for notice in notice_list],
        )
    carousel = CarouselComponent()
    for i in range(0, len(notice_list), 4):
        items = notice_list[i:i+4]
        carousel_items = [notice_to_list_item(notice) for notice in items]
        carousel.add_item(
            ListCardComponent(
                header=header,
                items=carousel_items,
                max_items=4,
            )
        )
    return carousel
