"""Keycloak 인증 컨텍스트가 포함된 HTTP 클라이언트를 제공합니다."""

from typing import AsyncGenerator
from collections.abc import Mapping

from httpx import AsyncClient, Request


class XUserIDClient(AsyncClient):
    """Keycloak 사용자 정보를 헤더에 포함하여 요청을 전송하는 비동기 HTTP 클라이언트입니다.

    Args:
        user_sub (str | None): 요청 헤더에 포함할 Keycloak `sub` 값.
        access_token (str | None): `Authorization` 헤더에 넣을 액세스 토큰.
        token_type (str): `Authorization` 헤더에 사용할 토큰 유형.
        extra_headers (Mapping[str, str] | None): 매 요청에 추가할 기타 정적 헤더.

    Attributes:
        user_sub (str | None): 요청 헤더에 포함될 Keycloak `sub`.
        access_token (str | None): `Authorization` 헤더에 포함될 토큰.
        token_type (str): 토큰 유형(기본값: `Bearer`).
        extra_headers (dict[str, str]): 추가 헤더 모음.
    """

    def __init__(
        self,
        user_sub: str | None,
        *,
        access_token: str | None = None,
        token_type: str = "Bearer",
        extra_headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.user_sub = user_sub
        self.access_token = access_token
        self.token_type = token_type
        self.extra_headers = dict(extra_headers or {})

    async def send(self, request: Request, **kwargs):
        """요청 헤더에 Keycloak 정보를 추가한 뒤 전송합니다.

        Args:
            request (Request): 전송할 HTTP 요청 객체.
            **kwargs: 부모 클래스의 `send` 메서드에 전달할 추가 인자.

        Returns:
            httpx.Response: HTTP 응답 객체.
        """
        if self.user_sub:
            request.headers.setdefault("X-User-Sub", self.user_sub)
        if self.access_token:
            request.headers.setdefault(
                "Authorization", f"{self.token_type} {self.access_token}"
            )
        for header_key, header_value in self.extra_headers.items():
            request.headers.setdefault(header_key, header_value)
        return await super().send(request, **kwargs)


async def get_async_client() -> AsyncGenerator[AsyncClient, None]:
    """공용 비동기 HTTP 클라이언트를 생성합니다.

    Returns:
        AsyncClient: 인증 정보가 없는 기본 HTTP 클라이언트.
    """
    async with AsyncClient() as client:
        yield client
