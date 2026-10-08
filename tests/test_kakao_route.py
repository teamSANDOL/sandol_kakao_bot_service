import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from httpx import (
    ASGITransport,
    AsyncClient,
    ConnectTimeout,
    PoolTimeout,
    ReadTimeout,
    TimeoutException,
    WriteTimeout,
)

from app.config import Config
from app.utils.kakao import KakaoError
from app.utils.kakao_route import KakaoTimeoutRoute
from main import kakao_error_handler


@pytest.fixture
def kakao_app() -> FastAPI:
    app = FastAPI(exception_handlers={KakaoError: kakao_error_handler})
    app.router.route_class = KakaoTimeoutRoute
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["dependency", "sequential", "internal", "fast"])
async def test_request_budget(
    monkeypatch: pytest.MonkeyPatch, scenario: str, kakao_app: FastAPI
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", 0.1)
    app = kakao_app
    state = {"cleaned": False, "endpoint_started": False, "first_completed": False}

    async def resource() -> AsyncIterator[None]:
        try:
            if scenario == "dependency":
                await asyncio.sleep(1.0)
            yield
        finally:
            state["cleaned"] = True

    @app.post("/skill", tags=["internal"] if scenario == "internal" else [])
    async def skill(_resource: Annotated[None, Depends(resource)]) -> dict[str, str]:
        state["endpoint_started"] = True
        if scenario == "sequential":
            await asyncio.sleep(0.02)
            state["first_completed"] = True
            await asyncio.sleep(0.09)
        elif scenario == "internal":
            await asyncio.sleep(0.15)
        return {"result": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/skill")

    assert response.status_code == 200
    assert state["cleaned"] is True
    if scenario in {"dependency", "sequential"}:
        data = response.json()
        assert data["version"] == "2.0"
        assert (
            "처리 시간이 초과" in data["template"]["outputs"][0]["simpleText"]["text"]
        )
    else:
        assert response.json() == {"result": "ok"}
    if scenario == "dependency":
        assert state["endpoint_started"] is False
    elif scenario == "sequential":
        assert state["first_completed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_type", [TimeoutError, KakaoError])
async def test_route_preserves_endpoint_exceptions(
    exception_type: type[Exception],
) -> None:
    app = FastAPI()
    app.router.route_class = KakaoTimeoutRoute

    @app.post("/skill")
    async def skill() -> None:
        raise exception_type("endpoint error")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with pytest.raises(exception_type, match="endpoint error"):
            await client.post("/skill")


def test_app_registers_timeout_routes() -> None:
    from app.routers import (
        classroom_router,
        meal_router,
        notice_router,
        statics_router,
        user_router,
    )
    from main import app

    routers = [
        app.router,
        meal_router,
        notice_router,
        classroom_router,
        statics_router,
        user_router,
    ]
    routes = [
        route
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    skill_routes = [route for route in routes if "internal" not in (route.tags or [])]
    assert skill_routes
    assert all(isinstance(route, KakaoTimeoutRoute) for route in skill_routes)
    assert any(
        route.path == "/users/callback" and "internal" in route.tags for route in routes
    )


@pytest.mark.asyncio
async def test_timeout_cancels_parallel_tasks(
    monkeypatch: pytest.MonkeyPatch, kakao_app: FastAPI
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", 0.1)
    app = kakao_app
    started: set[str] = set()
    cleaned: set[str] = set()
    wait = asyncio.Event()

    async def downstream(name: str) -> None:
        started.add(name)
        try:
            await wait.wait()
        finally:
            cleaned.add(name)

    @app.post("/skill")
    async def skill() -> dict[str, str]:
        await asyncio.gather(
            downstream("lunch"), downstream("dinner"), return_exceptions=True
        )
        return {"result": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/skill")

    assert response.status_code == 200
    assert response.json()["version"] == "2.0"
    assert started == {"lunch", "dinner"}
    assert cleaned == started


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route_name", ["meal_submit", "notice_list", "meal_manager_apply"]
)
async def test_timeout_message_depends_on_route_name(
    monkeypatch: pytest.MonkeyPatch, kakao_app: FastAPI, route_name: str
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", 0.01)

    @kakao_app.post("/changed-prefix/action", name=route_name)
    async def skill() -> None:
        await asyncio.Event().wait()

    async with AsyncClient(
        transport=ASGITransport(app=kakao_app), base_url="http://test"
    ) as client:
        response = await client.post("/changed-prefix/action")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2.0"
    message = data["template"]["outputs"][0]["simpleText"]["text"]
    if route_name == "meal_submit":
        assert message == (
            "처리 시간이 초과되어 등록 결과를 확인하지 못했습니다. "
            "점심/저녁 중 일부만 등록됐을 수 있으니 등록 상태를 먼저 확인해주세요."
        )
    else:
        assert message == "처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."


@pytest.mark.asyncio
async def test_timeout_raises_kakao_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", 0.01)
    app = FastAPI()
    app.router.route_class = KakaoTimeoutRoute

    @app.post("/skill")
    async def skill() -> None:
        await asyncio.Event().wait()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with pytest.raises(KakaoError, match="처리 시간이 초과") as error:
            await client.post("/skill")

    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_type", [ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout]
)
@pytest.mark.parametrize("route_name", ["notice_list", "meal_submit"])
async def test_downstream_timeout_uses_kakao_message(
    kakao_app: FastAPI, exception_type: type[TimeoutException], route_name: str
) -> None:
    @kakao_app.post("/skill", name=route_name)
    async def skill() -> None:
        raise exception_type("upstream timeout")

    async with AsyncClient(
        transport=ASGITransport(app=kakao_app), base_url="http://test"
    ) as client:
        response = await client.post("/skill")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2.0"
    message = data["template"]["outputs"][0]["simpleText"]["text"]
    if route_name == "meal_submit":
        assert "점심/저녁 중 일부만 등록됐을 수 있으니" in message
    else:
        assert message == "처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."


@pytest.mark.asyncio
async def test_internal_route_preserves_downstream_timeout(kakao_app: FastAPI) -> None:
    @kakao_app.post("/callback", tags=["internal"])
    async def callback() -> None:
        raise ReadTimeout("upstream timeout")

    async with AsyncClient(
        transport=ASGITransport(app=kakao_app), base_url="http://test"
    ) as client:
        with pytest.raises(ReadTimeout, match="upstream timeout"):
            await client.post("/callback")
