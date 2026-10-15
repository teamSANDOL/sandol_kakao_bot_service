"""TUK World 스킬 응답(목록 Carousel, 상세 카드) 조립 유틸입니다."""

from kakao_chatbot.response import ActionEnum, QuickReply
from kakao_chatbot.response.base import ParentComponent
from kakao_chatbot.response.components import (
    BasicCardComponent,
    CarouselComponent,
    Link,
    ListCardComponent,
    SimpleTextComponent,
    TextCardComponent,
    Thumbnail,
)

from app.config import Config
from app.schemas.tuk_world import TukWorldRestaurant

CATEGORIES = ("식당", "술집", "여가")

# 카카오 제약: Carousel 카드 10개, Carousel 안 ListCard 항목 4개, ListCard 버튼 2개,
# QuickReply 10개, ListItem 제목 35자, BasicCard 설명 230자, TextCard 설명 400자.
CARDS_PER_PAGE = 10
ITEMS_PER_CARD = 4
PAGE_SIZE = CARDS_PER_PAGE * ITEMS_PER_CARD
MAX_ITEM_TITLE = 35
MAX_ITEM_DESCRIPTION = 60
MAX_CARD_TITLE = 50
MAX_BASIC_DESCRIPTION = 230
MAX_TEXT_DESCRIPTION = 400
MAX_SIMPLE_TEXT = 1000
NO_DISCOUNT_INFO = "할인 정보가 없습니다."


def clip(text: str, limit: int) -> str:
    """limit자를 넘으면 말줄임표로 줄입니다."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_category(value: object, utterance: str = "") -> str | None:
    """extra 값이나 발화에서 분류를 찾습니다. 알 수 없으면 None(전체)입니다."""
    if isinstance(value, str) and value in CATEGORIES:
        return value
    return next((c for c in CATEGORIES if c in utterance), None)


def image_url(restaurant: TukWorldRestaurant) -> str | None:
    """업체 첫 이미지의 공개 절대 URL을 반환합니다. 없으면 None입니다."""
    if not restaurant.images:
        return None
    path = restaurant.images[0].url
    if path.startswith(("http://", "https://")):
        return path
    return f"{Config.STATIC_INFO_PUBLIC_URL}/{path.lstrip('/')}"


def _list_quick_replies(
    category: str | None, offset: int, has_more: bool
) -> list[QuickReply]:
    """분류 전환·더 보기 QuickReply를 만듭니다. 목록 블록이 없으면 발화로 대체합니다."""
    block_id = Config.TUK_WORLD_BLOCK_ID
    replies: list[QuickReply] = []
    for target in (None, *CATEGORIES):
        if target == category:
            continue
        label = "전체" if target is None else f"{target}만"
        if block_id:
            extra: dict[str, object] = {"category": target} if target else {}
            replies.append(
                QuickReply(label, ActionEnum.BLOCK, block_id=block_id, extra=extra)
            )
        else:
            text = f"TUK월드 {target}" if target else "TUK월드"
            replies.append(QuickReply(label, ActionEnum.MESSAGE, message_text=text))
    if has_more and block_id:
        extra = {"offset": offset + PAGE_SIZE}
        if category:
            extra["category"] = category
        replies.append(
            QuickReply("더 보기", ActionEnum.BLOCK, block_id=block_id, extra=extra)
        )
    return replies


def make_list_response(
    restaurants: list[TukWorldRestaurant], category: str | None, offset: int
) -> tuple[CarouselComponent, list[QuickReply]]:
    """업체 목록 한 페이지(최대 40곳)를 ListCard Carousel과 QuickReply로 만듭니다.

    Args:
        restaurants (list[TukWorldRestaurant]): 이미 분류로 거른 전체 목록
        category (str | None): 현재 분류. None이면 전체
        offset (int): 이번 페이지 시작 위치

    Returns:
        tuple[CarouselComponent, list[QuickReply]]: 목록 Carousel과 바로가기
    """
    page = restaurants[offset : offset + PAGE_SIZE]
    header = f"TUK World {category}" if category else "TUK World 제휴업체"
    carousel = CarouselComponent()
    for start in range(0, len(page), ITEMS_PER_CARD):
        card = ListCardComponent(header=header, max_items=ITEMS_PER_CARD)
        for r in page[start : start + ITEMS_PER_CARD]:
            description = " · ".join(filter(None, [r.category, r.address]))
            title = clip(r.name, MAX_ITEM_TITLE)
            desc = clip(description, MAX_ITEM_DESCRIPTION) or None
            if Config.TUK_WORLD_DETAIL_BLOCK_ID:
                card.add_item(
                    title=title,
                    description=desc,
                    image_url=image_url(r),
                    action="block",
                    block_id=Config.TUK_WORLD_DETAIL_BLOCK_ID,
                    extra={"id": r.id},
                )
            else:  # 상세 블록이 아직 없으면 카카오맵 링크로 대체
                link = Link(web=r.kakao_map_url) if r.kakao_map_url else None
                card.add_item(
                    title=title, description=desc, image_url=image_url(r), link=link
                )
        if start == 0 and Config.TUK_WORLD_MAP_URL:
            card.add_button(
                label="지도에서 보기",
                action="webLink",
                web_link_url=Config.TUK_WORLD_MAP_URL,
            )
        carousel.add_item(card)
    has_more = offset + PAGE_SIZE < len(restaurants)
    return carousel, _list_quick_replies(category, offset, has_more)


def make_detail_components(r: TukWorldRestaurant) -> list[ParentComponent]:
    """업체 상세를 BasicCard(이미지 없으면 TextCard)로 만듭니다.

    설명이 카드 글자 수 제한을 넘으면 카드엔 줄여 싣고 전문을 SimpleText로 덧붙입니다.

    Args:
        r (TukWorldRestaurant): 업체
    """
    text = r.discount_info or NO_DISCOUNT_INFO
    if r.address:
        text += f"\n\n주소: {r.address}"
    url = image_url(r)
    description = clip(text, MAX_BASIC_DESCRIPTION if url else MAX_TEXT_DESCRIPTION)
    title = clip(r.name, MAX_CARD_TITLE)
    card: BasicCardComponent | TextCardComponent
    if url:
        card = BasicCardComponent(Thumbnail(url), title=title, description=description)
    else:
        card = TextCardComponent(title=title, description=description)
    if r.kakao_map_url:
        card.add_button(
            label="카카오맵", action="webLink", web_link_url=r.kakao_map_url
        )
    if r.naver_map_url:
        card.add_button(
            label="네이버 지도", action="webLink", web_link_url=r.naver_map_url
        )
    if Config.TUK_WORLD_BLOCK_ID:
        card.add_button(
            label="목록으로", action="block", block_id=Config.TUK_WORLD_BLOCK_ID
        )
    else:
        card.add_button(label="목록으로", action="message", message_text="TUK월드")
    components: list[ParentComponent] = [card]
    if description != text:
        components.append(SimpleTextComponent(clip(text, MAX_SIMPLE_TEXT)))
    return components
