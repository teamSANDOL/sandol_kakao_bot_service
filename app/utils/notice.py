from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import ListCardComponent, ListItem, Link, CarouselComponent

from app.schemas.notice import Notice


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


def make_notice_response(
    notice_list: list[Notice],
) -> KakaoResponse:
    """공지사항 목록을 반환합니다."""
    response = KakaoResponse()
    if len(notice_list) == ListCardComponent(header="").max_items:
        return response.add_component(
            ListCardComponent(
                header="공지사항",
                items=[
                    notice_to_list_item(notice)
                    for notice in notice_list
                ],
            )
        )
    carousel = CarouselComponent()
    for i in range(0, len(notice_list), 4):
        items = notice_list[i:i+4]
        carousel_items = [
            notice_to_list_item(notice)
            for notice in items
        ]
        carousel.add_item(
            ListCardComponent(
                header="공지사항",
                items=carousel_items,
                max_items=4,
            )
        )
    response.add_component(carousel)
    return response
