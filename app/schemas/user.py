"""사용자/권한 관련 스키마를 정의합니다."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class KeycloakRealmAccess(BaseModel):
    """Keycloak Access Token의 Realm 접근 역할 정보."""

    roles: List[str] = Field(default_factory=list)


class KeycloakResourceAccess(BaseModel):
    """Keycloak Access Token의 Resource(Client) 접근 역할 정보."""

    # 예: {"account": {"roles": ["manage-account", ...]}, "sandol-meal-service": {"roles": ["meal_admin"]}}
    account: Optional[Dict[str, List[str]]] = None

    # Pydantic v2에서는 Extra='allow' 또는 동적 필드명 처리 필요
    # 여기서는 일반성을 위해 extra='allow' 사용
    class Config:
        """정의되지 않은 리소스 접근 키를 허용합니다."""

        extra = "allow"


class UserSchema(BaseModel):
    """Keycloak UserInfo 엔드포인트 및 Access Token 클레임 기반 사용자 정보 스키마.

    UserInfo 엔드포인트와 토큰 페이로드를 조합하여 생성됩니다.
    """

    # --- UserInfo 엔드포인트 제공 (표준 OIDC 프로필) ---
    sub: str = Field(..., description="Keycloak 사용자 고유 ID (Subject)")
    email: Optional[str] = Field(None, description="사용자 이메일")
    email_verified: bool = Field(False, description="이메일 인증 여부")
    name: Optional[str] = Field(None, description="전체 이름 (Full Name)")
    first_name: Optional[str] = Field(None, description="이름 (First Name)")
    last_name: Optional[str] = Field(None, description="성 (Last Name)")
    preferred_username: Optional[str] = Field(
        None, description="사용자 ID (로그인 시 사용)"
    )

    # --- Access Token 페이로드 제공 (역할 및 시간) ---
    realm_access: KeycloakRealmAccess = Field(
        default_factory=KeycloakRealmAccess, description="Realm 레벨 역할"
    )
    resource_access: KeycloakResourceAccess = Field(
        default_factory=KeycloakResourceAccess, description="Client(Resource) 레벨 역할"
    )

    class Config:
        """정의되지 않은 추가 필드도 허용합니다 (예: 커스텀 속성)."""

        extra = "allow"
