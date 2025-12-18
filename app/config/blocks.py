"""응답에 사용되는 상수들을 정의합니다."""

from copy import deepcopy
from enum import Enum
from typing import Optional

from kakao_chatbot.response import QuickReply, ActionEnum

# 도움말 QuickReply
HELP = QuickReply(label="도움말", message_text="도움말")


# 블록 ID 관리
class BlockID(str, Enum):
    CONFIRM = "6721838c369c0a05baca37a1"
    ADD_LUNCH_MENU = "672181220b8411112c75c884"
    ADD_DINNER_MENU = "672181305e0ed128077abf5e"
    MODIFY_MENU = "67218142369c0a05baca376c"
    DELETE_MENU = "67218366770f3e5a431708ac"
    DELETE_ALL_MENUS = "6721837657cc8a7ef53213ef"
    APPROVE_RESTAURANT = "6731d9b89fb8545410e9d29b"
    DECLINE_RESTAURANT = "674031c1aeded40bd4bd58d9"
    RESTAURANT_INFO = "672183965e0ed128077abfe3"
    SELECT_RESTAURANT = "67f3d3080e01a1241f2707c7"
    CLASSROOM_DETAIL = "683585d52a22a85698b931d5"
    LOGIN = "686a75d32036e951aa06169c"


def get_cafeteria_register_quick_replies(
    restaurant_name: Optional[str] = None,
) -> list[QuickReply]:
    """식당 등록 관련 QuickReply를 반환합니다.

    식당 등록과 관련된 QuickReply를 반환합니다. 각 QuickReply는
    ActionEnum.BLOCK을 사용하여 블록 ID와 연결됩니다.

    Returns:
        list[QuickReply]: 식당 등록 관련 QuickReply 리스트
    """
    if restaurant_name:
        qr_list = []
        for qr in deepcopy(CAFETERIA_REGISTER_QUICK_REPLIES):
            qr.extra = {
                "restaurant_name": restaurant_name,
            }
            qr_list.append(qr)
        return qr_list
    # 식당 이름이 없는 경우, 기본 QuickReply 리스트를 반환합니다.
    return CAFETERIA_REGISTER_QUICK_REPLIES


CAFETERIA_REGISTER_QUICK_REPLIES = [
    QuickReply("확정", ActionEnum.BLOCK, block_id=BlockID.CONFIRM),
    QuickReply("점심 메뉴 추가", ActionEnum.BLOCK, block_id=BlockID.ADD_LUNCH_MENU),
    QuickReply("저녁 메뉴 추가", ActionEnum.BLOCK, block_id=BlockID.ADD_DINNER_MENU),
    QuickReply("메뉴 수정", ActionEnum.BLOCK, block_id=BlockID.MODIFY_MENU),
]
