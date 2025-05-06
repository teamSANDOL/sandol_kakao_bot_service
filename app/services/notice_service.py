from typing import List, Optional

from app.config import Config
from app.schemas.notice import NoticeResponse, Notice
from app.utils.http import XUserIDClient


async def get_notice_list(
    client: XUserIDClient,
    page: Optional[int] = 1,
    page_size: Optional[int] = 20,
) -> List[Notice]:
    """공지사항 목록을 가져옵니다."""
    url = f"{Config.NOTICE_SERVICE_URL}/notice"

    response = await client.get(url)

    response.raise_for_status()

    return NoticeResponse(**response.json()).items
