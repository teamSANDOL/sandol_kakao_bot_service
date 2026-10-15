"""TUK World(총학생회 제휴 업체) static-info 응답 스키마."""

from pydantic import BaseModel, Field


class TukWorldImage(BaseModel):
    """업체 이미지. url은 static-info 기준 상대경로입니다."""

    id: int
    url: str


class TukWorldRestaurant(BaseModel):
    """제휴 업체 한 곳."""

    id: int
    name: str
    category: str | None = None
    address: str | None = None
    naver_map_url: str | None = None
    kakao_map_url: str | None = None
    discount_info: str | None = None
    images: list[TukWorldImage] = Field(default_factory=list)
