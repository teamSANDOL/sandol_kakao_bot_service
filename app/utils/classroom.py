"""강의실 관련 유틸리티 모듈입니다."""

import re
import string
from typing import List, Mapping, Protocol, TypeGuard, TypedDict, get_args

from kakao_chatbot.response.base import ParentComponent
from kakao_chatbot.response.components import (
    ItemCardComponent,
    Item,
    CarouselComponent,
    SimpleTextComponent,
    TextCardComponent,
)

from app.config import BlockID, logger
from app.schemas.classroom import BuildingName, DayName, EmptyClassroomInfo, Classroom
from app.utils.kakao import KakaoError, extract_text_value


class SupportsValueOrOrigin(Protocol):
    """`value` 또는 `origin` 속성을 가지는 입력 타입 프로토콜."""

    value: object
    origin: object


DayParamValue = str | Mapping[str, object] | SupportsValueOrOrigin


class ClassroomPayload(TypedDict):
    """빈 강의실 상세 payload 내 단일 강의실 항목 타입."""

    room_name: str


class EmptyClassroomInfoPayload(TypedDict, total=False):
    """client_extra.empty_classroom_info의 허용 payload 타입."""

    building: BuildingName
    empty_classrooms: list[ClassroomPayload]
    empty_classrooms_by_floor: dict[int, list[ClassroomPayload]]


def is_day_name(value: str) -> TypeGuard[DayName]:
    """문자열이 허용된 요일 형식인지 검사합니다."""
    return value in get_args(DayName)


def parse_day_name(value: DayParamValue) -> DayName | None:
    """detail param value에서 요일 문자열을 추출하고 형식을 검증합니다."""
    day = extract_text_value(value)
    if day is None:
        return None
    if is_day_name(day):
        return day
    return None


def parse_floor(room: str) -> int | None:
    """강의실 이름에서 층수를 추출합니다."""
    # 대강당은 1층으로 처리
    if room == "대강당":
        return 1

    # 606-1, 416-A, 210A 등 숫자로 시작하는 경우
    m = re.match(r"^(\d+)", room)
    if m:
        return int(m.group(1)) // 100  # 416 → 4층, 606 → 6층

    return None


def make_empty_classroom_component(
    empty_classrooms: EmptyClassroomInfo,
) -> ItemCardComponent:
    """빈 강의실 목록을 카카오톡 챗봇의 카드 형식으로 변환합니다.

    Args:
        empty_classrooms (EmptyClassroomInfo): 빈 강의실 정보

    Returns:
        ItemCardComponent: 빈 강의실 정보가 담긴 카드 컴포넌트
    """
    if not empty_classrooms.empty_classrooms:
        raise ValueError(f"{empty_classrooms.building}에 빈 강의실이 없습니다.")
    classrooms_by_floor: dict[int, List[Classroom]] = {}
    for classroom in empty_classrooms.empty_classrooms:
        floor = parse_floor(classroom.room_name)
        if floor is None:
            logger.warning(f"'{classroom.room_name}'의 형식이 잘못되어 무시되었습니다.")
            continue
        if floor in classrooms_by_floor:
            classrooms_by_floor[floor].append(classroom)
        else:
            classrooms_by_floor[floor] = [classroom]
    empty_classrooms.empty_classrooms_by_floor = dict(
        sorted(
            classrooms_by_floor.items(),
            key=lambda x: x[0],  # int 기준 정렬
        )
    )

    items: list[Item] = []
    for floor, classrooms in sorted(classrooms_by_floor.items()):
        if len(classrooms) > 1:
            description = f"{classrooms[0].room_name}외 {len(classrooms) - 1}개"
        else:
            description = classrooms[0].room_name
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
        extra={
            "empty_classroom_info": empty_classrooms.model_dump(),
        },
    )
    return card


def make_empty_classroom_components(
    empty_list: List[EmptyClassroomInfo],
) -> list[ParentComponent]:
    """빈 강의실 목록을 케로셀 형식으로 변환합니다.

    - 1개: 단일 카드
    - 2~10개: 하나의 Carousel
    - 11개 이상: 여러 Carousel
    - 없음: 안내 텍스트

    Args:
        empty_list (List[EmptyClassroomInfo]): 빈 강의실 정보 리스트

    Returns:
        list[ParentComponent]: 빈 강의실 정보가 담긴 카드/케로셀/텍스트 컴포넌트 리스트
    """
    if not empty_list:
        return [SimpleTextComponent(text="빈 강의실 정보가 없습니다.")]

    empty_list = sorted(empty_list, key=lambda x: (x.building == "미래", x.building))

    alphabet_components = []
    non_alphabet_components = []

    for empty_classrooms in empty_list:
        try:
            component = make_empty_classroom_component(empty_classrooms)
            if empty_classrooms.building[0] in string.ascii_letters:
                alphabet_components.append(component)
            else:
                non_alphabet_components.append(component)
        except ValueError as e:
            logger.warning(e)

    if not alphabet_components and not non_alphabet_components:
        return [SimpleTextComponent(text="빈 강의실 정보가 없습니다.")]

    result: list[ParentComponent] = []

    def to_carousels(
        components: list[ItemCardComponent],
    ) -> list[ParentComponent]:
        if not components:
            return []
        if len(components) == 1:
            return [components[0]]
        return [
            CarouselComponent(*components[i : i + 10])
            for i in range(0, len(components), 10)
        ]

    for grouped_component in to_carousels(alphabet_components):
        result.append(grouped_component)
    for grouped_component in to_carousels(non_alphabet_components):
        result.append(grouped_component)

    return result


def make_empty_classroom_detail_component(
    info: EmptyClassroomInfo | EmptyClassroomInfoPayload,
) -> CarouselComponent:
    """빈 강의실 상세 정보를 카드 형식으로 변환합니다.

    Args:
        info (str): 빈 강의실 정보 JSON 문자열

    Returns:
        CarouselComponent: 빈 강의실 상세 정보가 담긴 케로셀 컴포넌트
    """
    empty_classrooms = EmptyClassroomInfo.model_validate(info)
    if not empty_classrooms.empty_classrooms_by_floor:
        raise KakaoError(f"{empty_classrooms.building}에 빈 강의실이 없습니다.")

    # key를 int로 변환해서 정렬
    sorted_floors = sorted(
        ((int(k), v) for k, v in empty_classrooms.empty_classrooms_by_floor.items()),
        key=lambda x: x[0],
    )

    carousel = CarouselComponent()
    for floor, classrooms in sorted_floors:
        description = "\n".join(f"{classroom.room_name}" for classroom in classrooms)
        card = TextCardComponent(
            title=f"{empty_classrooms.building} {floor}층",
            description=description,
        )
        carousel.add_item(card)

    return carousel
