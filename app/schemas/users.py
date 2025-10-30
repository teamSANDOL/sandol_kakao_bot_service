from datetime import datetime
from pydantic import BaseModel, HttpUrl
from typing import Optional


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
    redirect_after: Optional[HttpUrl] = None


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

    relay_access_token: str
    issuer: str
    aud: str
    chatbot_user_id: str
    client_key: str
    ts: int
    nonce: str


class UserCreate(BaseModel):
    id: int
    kakao_id: str
    plusfriend_user_key: Optional[str] = None
    app_user_id: Optional[str] = None
    kakao_admin: bool = False


class UserRead(BaseModel):
    id: int
    kakao_id: str
    plusfriend_user_key: Optional[str]
    app_user_id: Optional[str]
    kakao_admin: bool

    class Config:
        from_attributes = True


class UserSchema(BaseModel):
    """사용자 정보를 나타내는 클래스입니다.

    Attributes:
        id (int): 사용자 ID
        name (str): 사용자 이름
        email (str): 사용자 이메일
        global_admin (bool) = 전역 관리자 여부
        service_account (bool) = 서비스 API 계정 여부
        created_at (datetime): 생성 시간
    """

    id: int
    name: str
    email: str
    global_admin: bool = False
    service_account: bool = False
    created_at: datetime

    class Config:
        """정의되지 않은 필드도 허용합니다."""

        extra = "allow"
