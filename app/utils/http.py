"""이 모듈은 HTTP 비동기 클라이언트를 생성하는 유틸리티 함수를 제공합니다."""

from typing import Optional

from httpx import AsyncClient, Request


class XUserIDClient(AsyncClient):
    """XUserIDClient 클래스는 비동기 HTTP 클라이언트로, 요청 헤더에 사용자 ID를 포함하여 전송합니다.

    Attributes:
        user_id (Optional[int]): 요청 헤더에 포함될 사용자 ID (없을 수 있음).

    Methods:
        __init__(user_id: Optional[int], *args, **kwargs):
            XUserIDClient 객체를 초기화합니다.
            사용자 ID와 추가적인 인자를 설정합니다.

        send(request: Request, **kwargs):
            요청 객체에 "X-User-ID" 헤더를 (존재할 경우) 추가한 후, 부모 클래스의 send 메서드를 호출합니다.
    """

    def __init__(self, user_id: Optional[int], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id

    async def send(self, request: Request, **kwargs):
        if self.user_id is not None:
            request.headers["X-User-ID"] = str(self.user_id)
        return await super().send(request, **kwargs)
