"""TUK World 목록·상세 스킬 테스트. static-info 호출은 httpx MockTransport로 대체합니다."""

from collections.abc import AsyncGenerator, Iterator
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

import main
from app.config import Config
from app.services import tuk_world_service
from app.utils.http import get_async_client

LIST_BLOCK = "list-block"
DETAIL_BLOCK = "detail-block"
CATEGORY_CYCLE = ("식당", "술집", "여가")


def _restaurant(idx: int, with_image: bool = False) -> dict[str, Any]:
    return {
        "id": idx,
        "name": f"업체{idx}",
        "category": CATEGORY_CYCLE[idx % 3],
        "address": f"경기도 시흥시 {idx}",
        "naver_map_url": f"https://naver.me/{idx}",
        "kakao_map_url": f"https://kko.to/{idx}",
        "latitude": 37.0,
        "longitude": 127.0,
        "discount_info": "10% 할인\n이용 조건: 학생증",
        "images": (
            [{"id": idx, "url": f"/static-info/tuk-world/images/{idx}"}]
            if with_image
            else []
        ),
    }


class _Upstream:
    def __init__(self) -> None:
        self.data: list[dict[str, Any]] = [_restaurant(i) for i in range(1, 43)]
        self.status = 200
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        assert request.url.path.endswith("/tuk-world/restaurants")
        return httpx.Response(self.status, json=self.data)


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Upstream]:
    up = _Upstream()
    tuk_world_service._cache.clear()
    monkeypatch.setattr(Config, "TUK_WORLD_BLOCK_ID", LIST_BLOCK)
    monkeypatch.setattr(Config, "TUK_WORLD_DETAIL_BLOCK_ID", DETAIL_BLOCK)
    monkeypatch.setattr(Config, "TUK_WORLD_MAP_URL", "https://map.example/tuk")
    monkeypatch.setattr(Config, "STATIC_INFO_PUBLIC_URL", "https://pub.example")

    async def _client() -> AsyncGenerator[httpx.AsyncClient, None]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(up.handler)) as c:
            yield c

    main.app.dependency_overrides[get_async_client] = _client
    yield up
    main.app.dependency_overrides.pop(get_async_client, None)
    tuk_world_service._cache.clear()


def _post(path: str, extra: dict[str, Any] | None = None, utterance: str = "") -> Any:
    body = {
        "action": {"params": {}, "detailParams": {}, "clientExtra": extra or {}},
        "userRequest": {
            "utterance": utterance,
            "user": {"id": "u1", "type": "botUserKey"},
        },
    }
    response = TestClient(main.app).post(f"/kakao-bot/tuk-world/{path}", json=body)
    assert response.status_code == 200
    return response.json()


def _carousel(body: dict[str, Any]) -> dict[str, Any]:
    return body["template"]["outputs"][0]["carousel"]


def test_list_all_paginates_with_more_quick_reply(upstream: _Upstream) -> None:
    body = _post("list")
    cards = _carousel(body)["items"]
    assert _carousel(body)["type"] == "listCard"
    assert len(cards) == 10
    assert all(len(c["items"]) == 4 for c in cards)
    first = cards[0]["items"][0]
    assert first["title"] == "업체1"
    assert first["action"] == "block"
    assert first["blockId"] == DETAIL_BLOCK
    assert first["extra"] == {"id": 1}
    assert cards[0]["buttons"][0]["webLinkUrl"] == "https://map.example/tuk"
    assert "buttons" not in cards[1]
    labels = [q["label"] for q in body["template"]["quickReplies"]]
    assert labels == ["식당만", "술집만", "여가만", "더 보기"]
    more = body["template"]["quickReplies"][-1]
    assert more["blockId"] == LIST_BLOCK
    assert more["extra"] == {"offset": 40}


def test_list_second_page_has_rest_and_no_more(upstream: _Upstream) -> None:
    body = _post("list", {"offset": "40"})
    cards = _carousel(body)["items"]
    assert sum(len(c["items"]) for c in cards) == 2
    assert "더 보기" not in [q["label"] for q in body["template"]["quickReplies"]]


def test_list_category_filters_and_switches(upstream: _Upstream) -> None:
    body = _post("list", {"category": "술집"})
    items = [i for c in _carousel(body)["items"] for i in c["items"]]
    assert items
    assert all("술집" in i["description"] for i in items)
    labels = [q["label"] for q in body["template"]["quickReplies"]]
    assert labels == ["전체", "식당만", "여가만"]
    assert body["template"]["quickReplies"][1]["extra"] == {"category": "식당"}


def test_list_category_from_utterance(upstream: _Upstream) -> None:
    body = _post("list", utterance="TUK월드 여가")
    items = [i for c in _carousel(body)["items"] for i in c["items"]]
    assert all("여가" in i["description"] for i in items)


def test_list_image_url_is_absolute_and_optional(upstream: _Upstream) -> None:
    upstream.data[0] = _restaurant(1, with_image=True)
    items = _carousel(_post("list"))["items"][0]["items"]
    assert items[0]["imageUrl"] == "https://pub.example/static-info/tuk-world/images/1"
    assert "imageUrl" not in items[1]


def test_list_hides_map_button_and_falls_back_without_ids(
    upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Config, "TUK_WORLD_MAP_URL", "")
    monkeypatch.setattr(Config, "TUK_WORLD_BLOCK_ID", "")
    monkeypatch.setattr(Config, "TUK_WORLD_DETAIL_BLOCK_ID", "")
    body = _post("list")
    card = _carousel(body)["items"][0]
    assert "buttons" not in card
    assert card["items"][0]["link"]["web"] == "https://kko.to/1"
    replies = body["template"]["quickReplies"]
    assert replies[0]["action"] == "message"
    assert replies[0]["messageText"] == "TUK월드 식당"
    assert "더 보기" not in [q["label"] for q in replies]


def test_detail_with_image_basic_card(upstream: _Upstream) -> None:
    upstream.data[4] = _restaurant(5, with_image=True)
    body = _post("detail", {"id": 5})
    card = body["template"]["outputs"][0]["basicCard"]
    assert card["title"] == "업체5"
    assert card["thumbnail"]["imageUrl"].endswith("/images/5")
    assert "10% 할인\n이용 조건: 학생증" in card["description"]
    assert "주소: 경기도 시흥시 5" in card["description"]
    buttons = card["buttons"]
    assert [b["label"] for b in buttons] == ["카카오맵", "네이버 지도", "목록으로"]
    assert buttons[0]["webLinkUrl"] == "https://kko.to/5"
    assert buttons[2]["blockId"] == LIST_BLOCK


def test_detail_without_image_long_text_adds_full_text(upstream: _Upstream) -> None:
    long_info = "혜택" * 300
    upstream.data[1]["discount_info"] = long_info
    outputs = _post("detail", {"id": "2"})["template"]["outputs"]
    card = outputs[0]["textCard"]
    assert len(card["description"]) == 400
    assert long_info in outputs[1]["simpleText"]["text"]


def test_detail_unknown_id_is_kakao_error_200(upstream: _Upstream) -> None:
    body = _post("detail", {"id": 9999})
    assert "찾을 수 없습니다" in body["template"]["outputs"][0]["simpleText"]["text"]


@pytest.mark.parametrize("path", ["list", "detail"])
def test_upstream_failure_is_kakao_error_200(upstream: _Upstream, path: str) -> None:
    upstream.status = 503
    body = _post(path, {"id": 1})
    assert "불러오지 못했습니다" in body["template"]["outputs"][0]["simpleText"]["text"]


def test_upstream_is_cached(upstream: _Upstream) -> None:
    _post("list")
    _post("detail", {"id": 1})
    assert upstream.calls == 1
