"""Keycloak 인증 컨텍스트가 포함된 HTTP 클라이언트를 제공합니다."""

from collections.abc import Mapping
from typing import AsyncGenerator

from httpx import AsyncClient, Request, Timeout

from app.config import Config


def get_downstream_timeout() -> Timeout:
    """응답 처리 여유를 남기도록 전체 예산보다 짧은 HTTP 단계별 대기를 반환한다."""
    return Timeout(
        Config.DOWNSTREAM_HTTP_TIMEOUT_SECONDS,
        connect=Config.DOWNSTREAM_HTTP_CONNECT_TIMEOUT_SECONDS,
    )


class XUserIDClient(AsyncClient):
    """Keycloak 사용자 정보를 헤더에 포함하여 요청을 전송하는 비동기 HTTP 클라이언트입니다.

    Config 기준 기본 timeout은 connect 1초, read/write/pool 각각 3초다.
    호출자가 timeout을 지정하면 해당 값을 사용하며 전체 요청 시간 제한은 아니다.

    Args:
        user_id (str | None): 요청 헤더에 포함할 Keycloak `id` 값.
        access_token (str | None): `Authorization` 헤더에 넣을 액세스 토큰.
        token_type (str): `Authorization` 헤더에 사용할 토큰 유형.
        extra_headers (Mapping[str, str] | None): 매 요청에 추가할 기타 정적 헤더.

    Attributes:
        user_id (str | None): 요청 헤더에 포함될 Keycloak `id`.
        access_token (str | None): `Authorization` 헤더에 포함될 토큰.
        token_type (str): 토큰 유형(기본값: `Bearer`).
        extra_headers (dict[str, str]): 추가 헤더 모음.
    """

    def __init__(
        self,
        user_id: str | None,
        *,
        access_token: str | None = None,
        token_type: str = "Bearer",
        extra_headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> None:
        """클라이언트를 초기화하고 헤더 주입용 컨텍스트를 저장합니다."""
        kwargs.setdefault("follow_redirects", True)
        kwargs.setdefault("timeout", get_downstream_timeout())
        super().__init__(**kwargs)
        self.user_id = user_id
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
        if self.user_id:
            request.headers.setdefault("X-User-ID", self.user_id)
        if self.access_token:
            request.headers.setdefault(
                "Authorization", f"{self.token_type} {self.access_token}"
            )
        for header_key, header_value in self.extra_headers.items():
            request.headers.setdefault(header_key, header_value)
        return await super().send(request, **kwargs)


async def get_async_client() -> AsyncGenerator[AsyncClient, None]:
    """공용 비동기 HTTP 클라이언트를 생성합니다.

    Config 기준 기본 timeout은 connect 1초, read/write/pool 각각 3초다.
    각 값은 환경 변수로 조정하며 전체 요청 시간 제한은 아니다.

    Returns:
        AsyncClient: 인증 정보가 없는 기본 HTTP 클라이언트.
    """
    async with AsyncClient(
        follow_redirects=True, timeout=get_downstream_timeout()
    ) as client:
        yield client
