from typing import List, Optional

from app.config import Config, logger
from app.schemas.notice import NoticeResponse, Notice
from app.utils.http import XUserIDClient


async def get_notice_list(
    client: XUserIDClient,
    page: Optional[int] = 1,
    page_size: Optional[int] = 20,
    raise_on_error: bool = False,
) -> List[Notice]:
    """공지사항 목록을 가져옵니다."""
    url = f"{Config.NOTICE_SERVICE_URL}/notice"
    params = {
        "page": page,
        "size": page_size,
    }
    response = await client.get(url, params=params)
    if response.status_code != Config.HttpStatus.OK:
        logger.error(f"Error: {response.status_code} - {response.text}")
        if raise_on_error:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return []

    return NoticeResponse(**response.json()).items


async def get_dorm_notice_list(
    client: XUserIDClient,
    page: Optional[int] = 1,
    page_size: Optional[int] = 20,
    raise_on_error: bool = False,
) -> List[Notice]:
    """기숙사 공지사항 목록을 가져옵니다."""
    url = f"{Config.NOTICE_SERVICE_URL}/dormitory-notice"
    params = {
        "page": page,
        "size": page_size,
    }
    response = await client.get(url, params=params)
    if response.status_code != Config.HttpStatus.OK:
        logger.error(f"Error: {response.status_code} - {response.text}")
        if raise_on_error:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return []

    return NoticeResponse(**response.json()).items


async def get_notice_by_author(
    client: XUserIDClient,
    author: str,
    size: int = 20,
    search_page_size: int = 50,
) -> List[Notice]:
    """특정 작성자의 공지사항 목록을 가져옵니다.

    공지사항을 계속해서 가져와서 작성자가 같은 공지사항을 찾습니다.
    작성자가 같은 공지사항이 size 만큼 모일 때까지 계속해서 가져옵니다.

    Args:
        client (XUserIDClient): XUserIDClient 인스턴스
        author (str): 작성자 이름
        size (int, optional): 가져올 공지사항 개수. Defaults to 20.
        search_page_size (int, optional): 한 번에 가져올 공지사항 개수. Defaults to 50.

    Returns:
        List[Notice]: 작성자가 같은 공지사항 목록
    """
    authors_notice_list: List[Notice] = []
    page = 1
    while len(authors_notice_list) < size:
        notice_list = await get_notice_list(
            client=client, page=page, page_size=search_page_size
        )
        authors_notice_list.extend(
            [notice for notice in notice_list if notice.author == author]
        )
        if len(notice_list) < search_page_size:
            break
        page += 1
        logger.info(
            f"page: {page}, size: {size}, len authors_notice_list: {len(authors_notice_list)}"
        )
    return authors_notice_list
