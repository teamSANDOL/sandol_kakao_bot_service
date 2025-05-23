"""공지사항 API를 통해 공지사항을 가져오는 API입니다.

일반 공지사항과 기숙사 공지사항을 가져오는 API를 활용합니다.
"""

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
    """공지사항 목록을 가져옵니다.

    공지사항 목록을 가져와 리스트 카드 형태로 반환합니다.
    공지사항이 없는 경우 "공지사항이 없습니다."라는 메시지를 반환합니다.
    """
    url = f"{Config.NOTICE_SERVICE_URL}/notice"
    params = {
        "page": page,
        "size": page_size,
    }
    logger.debug(f"Requesting notice list: url={url}, params={params}")
    response = await client.get(url, params=params)
    logger.debug(f"Received response: status={response.status_code}")

    if response.status_code != Config.HttpStatus.OK:
        logger.error(f"Error: {response.status_code} - {response.text}")
        if raise_on_error:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return []

    notice_response = NoticeResponse(**response.json())
    logger_data = [
        f"Notice ID: {item.id}, Title: {item.title}" for item in notice_response.items
    ]
    logger.debug(f"Parsed dorm notices: {logger_data}")
    return notice_response.items


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
    logger.debug(f"Requesting dorm notice list: url={url}, params={params}")
    response = await client.get(url, params=params)
    logger.debug(f"Received response: status={response.status_code}")

    if response.status_code != Config.HttpStatus.OK:
        logger.error(f"Error: {response.status_code} - {response.text}")
        if raise_on_error:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return []

    notice_response = NoticeResponse(**response.json())
    logger_data = [
        f"Notice ID: {item.id}, Title: {item.title}" for item in notice_response.items
    ]
    logger.debug(f"Parsed dorm notices: {logger_data}")
    return notice_response.items


async def get_notice_by_author(
    client: XUserIDClient,
    author: str,
    size: int = 20,
    search_page_size: int = 50,
    is_dormitory: bool = False,
) -> List[Notice]:
    """특정 작성자의 공지사항 목록을 가져옵니다."""
    authors_notice_list: List[Notice] = []
    page = 1
    while len(authors_notice_list) < size:
        logger.debug(f"Fetching page {page} for author '{author}'")
        if is_dormitory:
            notice_list = await get_dorm_notice_list(
                client=client, page=page, page_size=search_page_size
            )
        else:
            notice_list = await get_notice_list(
                client=client, page=page, page_size=search_page_size
            )
        filtered = [notice for notice in notice_list if author in notice.author]
        logger.debug(f"Filtered {len(filtered)} notices by author")
        authors_notice_list.extend(filtered)
        if len(notice_list) < search_page_size:
            logger.debug("Reached last page of notices")
            break
        page += 1
        logger.info(
            f"page: {page}, size: {size}, len authors_notice_list: {len(authors_notice_list)}"
        )
    return authors_notice_list
