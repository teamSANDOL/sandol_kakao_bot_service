"""인증/로그인 링크 발급 및 콜백 요청 스키마를 정의합니다."""

from typing import Optional

from pydantic import BaseModel, HttpUrl, field_validator

from app.validators.redirects import normalize_optional_relative_path


class IssueLinkReq(BaseModel):
    """로그인 링크 발급 요청 스키마를 정의한다.

    Attributes:
        chatbot_user_id (str): 챗봇 내부 사용자 ID.
        callback_url (HttpUrl): 챗봇 서버 콜백 URL(서버 간 POST 수신).
        client_key (str): relay에 등록된 클라이언트 키.
        redirect_after (Optional[str]): 로그인 완료 후 사용자 브라우저 최종 리다이렉트 목적지.
    """

    chatbot_user_id: str
    callback_url: HttpUrl
    client_key: str
    redirect_after: Optional[str] = None

    @field_validator("redirect_after", mode="before")
    @classmethod
    def validate_redirect_after(cls, value: object) -> Optional[str]:
        """로그인 후 이동 경로를 auth-relay 정책과 동일하게 검증한다."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("redirect_after must be a string.")
        return normalize_optional_relative_path(value)


class IssueLinkRes(BaseModel):
    """로그인 링크 발급 응답 스키마를 정의한다.

    Attributes:
        login_link (str): 사용자 브라우저가 열어야 할 로그인 시작 URL.
        expires_in (int): 링크 만료까지 남은 시간(초).
    """

    login_link: str
    expires_in: int


class LoginCallbackReq(BaseModel):
    """로그인 콜백 요청 스키마를 정의한다.

    Attributes:
        relay_access_token (str): relay 액세스 토큰.
        issuer (str): 토큰 발급자.
        aud (str): 토큰 대상자.
        chatbot_user_id (str): 챗봇 내부 사용자 ID.
        client_key (str): relay에 등록된 클라이언트 키.
        ts (int): 토큰 발급 시간(UNIX 타임스탬프).
        nonce (str): 재생 공격 방지를 위한 임의 문자열.
    """

    issuer: str
    aud: str
    chatbot_user_id: str
    client_key: str
    relay_access_token: str
    offline_refresh_token: str
    expires_in: int = 60
    refresh_expires_in: int = ((60 * 60) * 24) * 30  # 30일
    ts: int
    nonce: str
