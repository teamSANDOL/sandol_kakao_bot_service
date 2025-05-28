from collections.abc import Sequence
import json
import re
from datetime import datetime
from typing import Annotated, List, Optional, overload

from fastapi import Depends
from fastapi.responses import JSONResponse
from kakao_chatbot import Payload
from kakao_chatbot.context import Context, ContextParam
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import (
    ItemCardComponent,
    Item,
    CarouselComponent,
    SimpleTextComponent,
)

from app.config import BlockID, logger
from app.schemas.classroom import EmptyClassroomInfo, Classroom
from app.utils import get_korean_day
from app.utils.user import get_current_user
from app.utils.http import XUserIDClient
from app.utils.kakao import KakaoError, parse_payload

# 방 번호에서 앞자리(층)와 뒤 2자리(호실)를 분리하는 정규식
pattern = re.compile(r'^(\d+)(\d{2})호$')

def parse_floor(room: str) -> int | None:
    m = pattern.match(room)
    return int(m.group(1)) if m else None


def make_empty_classroom_component(
    empty_classrooms: EmptyClassroomInfo,
) -> ItemCardComponent:
    """빈 강의실 목록을 카카오톡 챗봇의 카드 형식으로 변환합니다."""
    if not empty_classrooms.empty_classrooms:
        raise ValueError(
            f"{empty_classrooms.building}에 빈 강의실이 없습니다."
        )
    classrooms_by_floor: dict[int, List[Classroom]] = {}
    for classroom in empty_classrooms.empty_classrooms:
        floor = parse_floor(classroom.room_name)
        if floor is None:
            logger.warning(
                f"'{classroom.room_name}'의 형식이 잘못되어 무시되었습니다."
            )
            continue
        if floor in classrooms_by_floor:
            classrooms_by_floor[floor].append(classroom)
        else:
            classrooms_by_floor[floor] = [classroom]
    items: list[Item] = []
    for floor, classrooms in sorted(classrooms_by_floor.items()):
        if len(classrooms) > 1:
            description=f"{classrooms[0].room_name}외 {len(classrooms) - 1}개"
        else:
            description=classrooms[0].room_name
        items.append(
            Item(
                title=f"{floor}층",
                description=description,
            )
        )
    card = ItemCardComponent(
        title=empty_classrooms.building,
        item_list=items,
    )
    card.add_button(
        label="자세히 보기",
        action="block",
        block_id=BlockID.CLASSROOM_DETAIL,
    )
    return card

def make_empty_classroom_components(
    empty_list: List[EmptyClassroomInfo],
) -> List[ItemCardComponent] | List[CarouselComponent] | List[SimpleTextComponent]:
    """빈 강의실 목록을 캐러셀 형식으로 변환합니다.

    - 1개: 단일 카드
    - 2~10개: 하나의 Carousel
    - 11개 이상: 여러 Carousel
    - 없음: 안내 텍스트
    """
    if not empty_list:
        return [SimpleTextComponent(text="빈 강의실 정보가 없습니다.")]

    empty_list = sorted(
        empty_list,
        key=lambda x: (x.building == "미래", x.building)
    )

    components = []
    for empty_classrooms in empty_list:
        try:
            components.append(
                make_empty_classroom_component(empty_classrooms)
            )
        except ValueError as e:
            logger.warning(e)

    if not components:
        return [SimpleTextComponent(text="빈 강의실 정보가 없습니다.")]

    if len(components) == 1:
        return [components[0]]

    carousels = []
    for i in range(0, len(components), 10):
        carousels.append(CarouselComponent(*components[i:i+10]))

    return carousels
