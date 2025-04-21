"""학교 조직 정보 및 셔틀버스 이미지 링크를 가져오는 서비스 모듈"""
from typing import List, Optional, Union

from app.config import Config, logger
from app.schemas.statics import (
    OrganizationUnit,
    OrganizationGroup,
    OrganizationType,
    UniversityStructure,
)
from app.utils.http import XUserIDClient


def parse_organization(
        obj: dict) -> Union[OrganizationUnit, OrganizationGroup]:
    """dict → Pydantic 조직 객체로 변환"""
    if obj.get("type") == "unit":
        return OrganizationUnit(**obj)
    if obj.get("type") == "group":
        return OrganizationGroup(**obj)
    raise ValueError(f"Unknown organization type: {obj.get('type')}")


async def fetch_university_structure(
    client: XUserIDClient,
) -> UniversityStructure:
    """학교 조직 정보를 가져오는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스

    Returns:
        UniversityStructure: 학교 조직 정보
    """
    response = await client.get(
        f"{Config.STATIC_INFO_SERVICE_URL}/organization/tree"
    )
    response.raise_for_status()
    response_json = response.json()
    logger.debug(f"Fetched university structure: {response_json}")
    return UniversityStructure.model_validate(response_json)


async def search_organization(
    client: XUserIDClient,
    name: str,
) -> Optional[OrganizationType]:
    """조직 이름으로 조직을 검색하는 함수

    Returns:
        Optional[OrganizationUnit | OrganizationGroup]
    """
    response = await client.get(
        f"{Config.STATIC_INFO_SERVICE_URL}/organization/{name}",
    )
    response.raise_for_status()
    response_json = response.json()
    logger.debug(f"Fetched organization: {response_json}")

    try:
        items = (
            [parse_organization(response_json)]
            if isinstance(response_json, dict)
            else [parse_organization(obj) for obj in response_json]
        )
    except Exception as e:
        logger.warning(f"조직 파싱 실패: {e}")
        return None

    return items[0] if items else None


async def fetch_shuttle_img_inks(
    client: XUserIDClient,
) -> List[str]:
    """셔틀버스 이미지 링크 리스트를 가져오는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스

    Returns:
        List[str]: 셔틀버스 이미지 링크 리스트
    """
    response = await client.get(
        f"{Config.STATIC_INFO_SERVICE_URL}/bus/images",
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    response_json = response.json()
    logger.debug(f"Fetched shuttle image links: {response_json}")
    return response_json.get("image_urls", [])
