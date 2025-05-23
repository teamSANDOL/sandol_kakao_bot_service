from kakao_chatbot.response import KakaoResponse
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
    """공지사항을 리스트 아이템으로 변환합니다."""
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

    Args:
        notice_list (list[Notice]): 공지사항 목록
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
