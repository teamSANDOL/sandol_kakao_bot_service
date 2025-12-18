"""사용자 관련 공통 유틸리티."""

from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import (
    Button,
    ItemCardComponent,
    TextCardComponent,
)

from app.schemas.user import UserSchema
from app.schemas.auth import IssueLinkRes


async def make_login_link_response(link: IssueLinkRes) -> KakaoResponse:
    """로그인 링크 응답을 생성합니다."""
    response = KakaoResponse()
    card = TextCardComponent(
        title="로그인 링크",
        description=(
            f"아래 버튼을 눌러 로그인 페이지로 이동하세요. "
            f"로그인 링크는 {link.expires_in}초 후 만료됩니다."
        ),
    )
    button = Button(
        action="webLink",
        label="로그인 하러 가기",
        web_link_url=link.login_link,
    )
    card.add_button(button)
    response.add_component(card)
    return response


async def make_user_info_response(user: UserSchema) -> KakaoResponse:
    """사용자 정보 응답을 생성합니다."""
    response = KakaoResponse()
    item_card = ItemCardComponent(
        item_list=[],
        title="사용자 정보",
        description="현재 로그인된 사용자의 정보입니다.",
    )
    item_card.add_item("성명", user.name if user.name else "등록되지 않음")
    item_card.add_item("이메일", user.email if user.email else "등록되지 않음")
    item_card.add_item(
        "이메일 인증 상태", "인증됨" if user.email_verified else "미인증"
    )
    response.add_component(item_card)
    return response
