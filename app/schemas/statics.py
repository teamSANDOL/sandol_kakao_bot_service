"""학교 조직 정보의 스키마를 정의하는 모듈"""
from typing import Dict, Literal, Optional, Union

from pydantic import BaseModel


class OrganizationUnit(BaseModel):
    """조직의 기본 단위 (전화번호, URL 등 포함)

    Attributes:
        name (str): 조직 이름
        phone (Optional[str]): 전화번호
        url (Optional[str]): URL, 홈페이지 주소
    """

    type: Literal["unit"] = "unit"
    name: str
    phone: Optional[str] = None
    url: Optional[str] = None


class OrganizationGroup(BaseModel):
    """하위 조직을 포함할 수 있는 조직 단위 (대학본부, 단과대학 등)"""

    type: Literal["group"] = "group"
    name: str
    subunits: Dict[str, Union["OrganizationUnit", "OrganizationGroup"]] = {}

    def as_list(self) -> list[Union["OrganizationUnit", "OrganizationGroup"]]:
        """하위 조직을 리스트로 반환"""
        return list(self.subunits.values())


class UniversityStructure(BaseModel):
    """학교 전체 조직 구조를 관리하는 클래스"""

    type: Literal["root"] = "root"
    root: Union[OrganizationGroup, OrganizationUnit]


# discriminator 기반 Union
OrganizationType = Union[OrganizationUnit, OrganizationGroup]
