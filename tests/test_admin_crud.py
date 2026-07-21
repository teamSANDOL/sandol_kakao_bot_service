"""Admin 패널 User 테이블 CRUD 동작 테스트."""

import json
import os
import time

import pytest
import pytest_asyncio
from sqlalchemy import delete
from starlette.testclient import TestClient

os.environ.setdefault("KC_CLIENT_SECRET", "test-secret")

import main  # noqa: E402
from app.admin_auth import ADMIN_SESSION_COOKIE  # noqa: E402
from app.database import AsyncSessionLocal, init_db  # noqa: E402
from app.models.users import User  # noqa: E402
from app.utils.security import encrypt_token  # noqa: E402


@pytest.fixture
def admin_client() -> TestClient:
    """관리자 세션 쿠키가 설정된 TestClient를 반환합니다."""
    client = TestClient(main.app, base_url="https://testserver")
    client.cookies.set(
        ADMIN_SESSION_COOKIE,
        encrypt_token(json.dumps({"sub": "admin-sub", "exp": int(time.time()) + 600})),
    )
    return client


@pytest_asyncio.fixture(autouse=True)
async def seed_users():
    """테스트용 사용자 두 명을 넣고 테스트 후 테이블을 비웁니다."""
    await init_db()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(User))
            session.add(
                User(keycloak_id="kc-1", kakao_id="kakao-1", kakao_admin=False)
            )
            session.add(User(keycloak_id="kc-2", kakao_id="kakao-2", kakao_admin=True))
    yield
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(User))


@pytest.mark.asyncio
async def test_list_renders_and_delete_url_uses_https(admin_client: TestClient):
    response = admin_client.get("/kakao-bot/admin/user/list")
    assert response.status_code == 200
    assert "kakao-1" in response.text
    # 삭제 버튼의 AJAX URL이 https로 생성되어야 브라우저 mixed content 차단을 피한다
    assert 'data-url="https://testserver/kakao-bot/admin/user/delete' in response.text


@pytest.mark.asyncio
async def test_delete_removes_row(admin_client: TestClient):
    list_page = admin_client.get("/kakao-bot/admin/user/list").text
    assert "kakao-2" in list_page

    response = admin_client.delete("/kakao-bot/admin/user/delete?pks=2")
    assert response.status_code == 200

    list_page = admin_client.get("/kakao-bot/admin/user/list").text
    assert "kakao-2" not in list_page
    assert "kakao-1" in list_page


@pytest.mark.asyncio
async def test_create_and_edit(admin_client: TestClient):
    response = admin_client.post(
        "/kakao-bot/admin/user/create",
        data={"keycloak_id": "kc-3", "kakao_id": "kakao-3", "kakao_admin": "false"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    response = admin_client.post(
        "/kakao-bot/admin/user/edit/1",
        data={"keycloak_id": "kc-1", "kakao_id": "kakao-1-edited", "kakao_admin": "true"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    list_page = admin_client.get("/kakao-bot/admin/user/list").text
    assert "kakao-3" in list_page
    assert "kakao-1-edited" in list_page


@pytest.mark.asyncio
async def test_unauthenticated_delete_redirects_to_keycloak():
    client = TestClient(main.app, base_url="https://testserver")
    response = client.delete(
        "/kakao-bot/admin/user/delete?pks=1", follow_redirects=False
    )
    assert response.status_code == 302
    assert "openid-connect/auth" in response.headers["location"]


@pytest.mark.asyncio
async def test_details_hides_encrypted_tokens(admin_client: TestClient):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                User(
                    keycloak_id="kc-token",
                    kakao_id="kakao-token",
                    kakao_admin=False,
                    access_token=encrypt_token("secret-access"),
                    refresh_token=encrypt_token("secret-refresh"),
                )
            )
    list_page = admin_client.get("/kakao-bot/admin/user/list").text
    pk = list_page.split("/kakao-bot/admin/user/details/")[1].split('"')[0]

    detail_page = admin_client.get(f"/kakao-bot/admin/user/details/{pk}").text
    assert "access_token" not in detail_page.replace("access_token_expires_at", "")
    assert "refresh_token" not in detail_page.replace("refresh_token_expires_at", "")
