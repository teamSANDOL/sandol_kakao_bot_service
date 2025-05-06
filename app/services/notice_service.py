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
    params = {
        "page": page,
        "size": page_size,
    }
    response = await client.get(url, params=params)
    if response.status_code != Config.HttpStatus.OK:
        # 기타 에러 처리
        raise Exception(f"Error: {response.status_code} - {response.text}")

    return NoticeResponse(**response.json()).items
