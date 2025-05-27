"""이 모듈은 교실 및 빈 강의실 정보를 나타내는 데이터 모델을 정의합니다."""
from typing import List, Literal

from pydantic import BaseModel, field_validator


BuildingName = Literal[
    "A동",
    "B동",
    "C동",
    "D동",
    "E동",
    "G동",
    "P동",
    "TIP",
    "미래",
    "비즈",
    "산융",
    "종합",
    "제2생",
    "중앙"
]


class Classroom(BaseModel):
    """교실의 정보를 저장하는 클래스입니다.

    Attributes:
        room_name (str): 교실의 이름을 나타냅니다.
    """
    room_name: str


class EmptyClassroomInfo(BaseModel):
    """건물별 빈 강의실 정보를 저장하는 모델입니다.

    Attributes:
        building (str): 건물 이름입니다.
        empty_classrooms (List[Classroom]): 빈 강의실 목록입니다.
    """
    building: BuildingName
    empty_classrooms: List[Classroom]

    @field_validator("empty_classrooms", mode="before")
    @classmethod
    def parse_classrooms(cls, v):
        """빈 강의실 목록을 파싱하여 적절한 형식으로 변환합니다.

        Args:
            v (Any): 원본 빈 강의실 목록 데이터입니다.

        Returns:
            Any: 변환된 빈 강의실 목록 데이터입니다.
        """
        # 원래 JSON이 ["103호", "104호"] 같은 형식이므로 변환
        if all(isinstance(item, str) for item in v):
            return [{"room_name": item} for item in v]
        return v
