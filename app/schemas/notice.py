from datetime import datetime

from pydantic import BaseModel, Field


class Notice(BaseModel):
    """공지사항 모델

    Attributes:
        id (int): 공지사항 ID
        url (str): 공지사항 URL
        title (str): 공지사항 제목
        author (str): 작성자
        createAt (str): 생성일시
    """

    id: int
    url: str
    title: str
    author: str
    create_at: datetime = Field(alias="createAt")

    class Config:
        """Pydantic 설정"""
        allow_population_by_field_name = True  # 역직렬화 시 필드명 사용 허용


class NoticeResponse(BaseModel):
    """공지사항 응답모델

    Attributes:
        items (list[Notice]): 공지사항 목록
        total (int): 총 공지사항 수
        page (int): 현재 페이지
        size (int): 페이지당 공지사항 수
    """
    items: list[Notice]
    total: int
    page: int
    size: int
