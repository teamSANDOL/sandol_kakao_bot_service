"""폴백 발화 수집 엔드포인트 테스트."""

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from starlette.testclient import TestClient

import main
from app.database import AsyncSessionLocal, init_db
from app.models.fallback import FallbackUtterance
from app.routers import fallback as fallback_module
from app.config import Config
from app.routers.fallback import (
    FALLBACK_MESSAGES,
    MAX_BODY_BYTES,
    MAX_FLOW_CHARS,
    MAX_PARAMS_CHARS,
    MAX_RAW_PAYLOAD_CHARS,
    MAX_UTTERANCE_LENGTH,
)

URL = "/kakao-bot/fallback"


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "bot": {"id": "bot-1", "name": "산돌이"},
        "action": {"params": {"a": "b"}, "detailParams": {}},
        "userRequest": {
            "utterance": "알수없는말",
            "callbackUrl": "https://callback.example/secret",
            "block": {"id": "blk-1", "name": "폴백 블록"},
            "user": {"id": "user-1", "type": "botUserKey"},
        },
        "flow": {
            "lastBlock": {"id": "last-1", "name": "직전 블록"},
            "trigger": {
                "type": "TEXT",
                "referrerBlock": {"id": "ref-1", "name": "참조 블록"},
                "access_token": "should-not-be-stored",
            },
        },
        "authorization_token": "should-not-be-stored",
    }
    body.update(overrides)
    return body


def _text(response: Any) -> str:
    return response.json()["template"]["outputs"][0]["simpleText"]["text"]


@pytest_asyncio.fixture(autouse=True)
async def clean_table():
    """테스트 전후로 fallback_utterances 테이블을 비웁니다."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(FallbackUtterance))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(FallbackUtterance))
        await session.commit()


async def _rows() -> list[FallbackUtterance]:
    async with AsyncSessionLocal() as session:
        return list((await session.scalars(select(FallbackUtterance))).all())


@pytest.mark.asyncio
async def test_saves_utterance_and_returns_message() -> None:
    response = TestClient(main.app).post(URL, json=_payload())

    assert response.status_code == 200
    assert _text(response) in FALLBACK_MESSAGES
    [row] = await _rows()
    assert row.utterance == "알수없는말"
    assert row.kakao_user_id == "user-1"
    assert row.block_name == "폴백 블록"
    assert row.bot_id == "bot-1"
    assert row.params == {"a": "b"}
    assert row.trigger_type == "TEXT"
    assert row.trigger_referrer_block_id == "ref-1"
    assert row.trigger_referrer_block_name == "참조 블록"
    assert row.flow is not None
    assert row.flow["lastBlock"]["id"] == "last-1"
    assert "access_token" not in row.flow["trigger"]
    assert row.raw_payload is not None
    assert "callbackUrl" not in row.raw_payload["userRequest"]
    assert "authorization_token" not in row.raw_payload


@pytest.mark.asyncio
async def test_payload_without_user_info() -> None:
    response = TestClient(main.app).post(
        URL, json={"userRequest": {"utterance": "익명"}}
    )

    assert response.status_code == 200
    [row] = await _rows()
    assert row.utterance == "익명"
    assert row.kakao_user_id is None
    assert row.block_id is None
    assert row.flow is None
    assert row.trigger_type is None


@pytest.mark.asyncio
async def test_long_utterance_is_truncated() -> None:
    body = _payload()
    body["userRequest"]["utterance"] = "가" * 2000
    TestClient(main.app).post(URL, json=body)

    [row] = await _rows()
    assert len(row.utterance) == MAX_UTTERANCE_LENGTH


@pytest.mark.asyncio
async def test_db_failure_still_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_session() -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(fallback_module, "AsyncSessionLocal", broken_session)
    response = TestClient(main.app).post(URL, json=_payload())

    assert response.status_code == 200
    assert _text(response) in FALLBACK_MESSAGES


@pytest.mark.asyncio
async def test_invalid_json_still_returns_200() -> None:
    response = TestClient(main.app).post(URL, content=b"not json")

    assert response.status_code == 200
    assert _text(response) in FALLBACK_MESSAGES
    assert await _rows() == []


def _quick_replies(response: Any) -> list[dict[str, Any]]:
    return response.json()["template"]["quickReplies"]


def test_help_quick_reply_message_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "HELP_BLOCK_ID", "")
    response = TestClient(main.app).post(URL, json=_payload())

    [reply] = _quick_replies(response)
    assert reply["label"] == "도움말"
    assert reply["action"] == "message"
    assert reply["messageText"] == "도움말"


def test_help_quick_reply_block_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "HELP_BLOCK_ID", "help-block-id")
    response = TestClient(main.app).post(URL, json=_payload())

    [reply] = _quick_replies(response)
    assert reply["action"] == "block"
    assert reply["blockId"] == "help-block-id"


@pytest.mark.asyncio
async def test_oversized_fields_are_stored_as_none() -> None:
    body = _payload()
    body["action"]["params"] = {"a": "x" * MAX_PARAMS_CHARS}
    body["action"]["detailParams"] = {"a": "x" * MAX_PARAMS_CHARS}
    body["flow"]["trigger"]["note"] = "x" * MAX_FLOW_CHARS
    response = TestClient(main.app).post(URL, json=body)

    assert response.status_code == 200
    [row] = await _rows()
    assert row.params is None
    assert row.detail_params is None
    assert row.flow is None
    assert row.utterance == "알수없는말"
    assert row.raw_payload is not None


@pytest.mark.asyncio
async def test_user_properties_removed_but_id_kept() -> None:
    body = _payload()
    body["userRequest"]["user"]["properties"] = {"plusfriendUserKey": "pk"}
    TestClient(main.app).post(URL, json=body)

    [row] = await _rows()
    assert row.raw_payload is not None
    user = row.raw_payload["userRequest"]["user"]
    assert user == {"id": "user-1", "type": "botUserKey"}
    assert row.kakao_user_id == "user-1"


@pytest.mark.asyncio
async def test_huge_body_skips_save_but_returns_200() -> None:
    body = _payload()
    body["userRequest"]["utterance"] = "가" * MAX_BODY_BYTES
    response = TestClient(main.app).post(URL, json=body)

    assert response.status_code == 200
    assert _text(response) in FALLBACK_MESSAGES
    assert await _rows() == []


@pytest.mark.asyncio
async def test_large_raw_payload_kept_up_to_limit() -> None:
    body = _payload()
    body["extra"] = {"pad": "x" * 40_000}
    TestClient(main.app).post(URL, json=body)

    [row] = await _rows()
    assert row.raw_payload is not None
    assert MAX_RAW_PAYLOAD_CHARS == 64 * 1024
