from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import ListCardComponent, ListItem, Link, CarouselComponent

from app.schemas.notice import Notice

def notice_to_list_item(notice: Notice) -> ListItem:
    """공지사항을 리스트 아이템으로 변환합니다."""
    description = f"{notice.author} | {notice.create_at}"
    return ListItem(
        title=notice.title,
        description=notice.description,
        link=Link(
            web=notice.url,
        ),
    )


def make_notice_response(
    notice_list: list[Notice],
) -> KakaoResponse:
    """공지사항 목록을 반환합니다."""
    response = KakaoResponse()
    if len(notice_list) == 5:
        return response.add_component(
            ListCardComponent(
                header="공지사항",
                items=[
                    notice_to_list_item(notice)
                    for notice in notice_list
                ],
            )
        )
    for i in range(0, len(notice_list), 5):
        carousel = CarouselComponent()
        items = notice_list[i:i+5]
        carousel_items = [
            notice_to_list_item(notice)
            for notice in items
        ]
        carousel.add_item(
            ListCardComponent(
                header="공지사항",
                items=carousel_items,
            )
        )
        response.add_component(carousel)
    return response
