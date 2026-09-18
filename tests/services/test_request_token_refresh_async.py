from types import SimpleNamespace

import pytest

from app.services import auth_service


@pytest.mark.asyncio
async def test_request_token_refresh_uses_async_keycloak_client(monkeypatch) -> None:
    """request_token_refresh가 동기 refresh_token이 아닌 a_refresh_token을 쓰는지 확인한다.

    async def 함수 안에서 python-keycloak의 동기 refresh_token(requests 기반
    블로킹 I/O)을 await 없이 호출하면 이벤트 루프 전체가 멈춘다
    (GitHub 이슈 teamSANDOL/sandol_kakao_bot_service#11). kc 목 객체에
    a_refresh_token만 정의해 두어, 구현이 동기 refresh_token 호출로
    되돌아가면 AttributeError로 이 테스트가 실패하도록 한다.
    """
    calls: list[str] = []

    async def fake_a_refresh_token(refresh_token: str) -> dict[str, object]:
        calls.append(refresh_token)
        return {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 300,
            "refresh_expires_in": 3600,
        }

    kc = SimpleNamespace(a_refresh_token=fake_a_refresh_token)
    monkeypatch.setattr(auth_service, "get_keycloak_client", lambda: kc)

    result = await auth_service.request_token_refresh("old-refresh-token")

    assert result["access_token"] == "new-access-token"
    assert calls == ["old-refresh-token"]
