import json

from app.utils.kakao import dump_kakao_value_json, to_jsonable_kakao_value


class FakeParam:
    def __init__(self) -> None:
        self.origin: str = "김치찌개"
        self.value: dict[str, str] = {
            "value": "김치찌개",
            "resolved_value": "김치찌개",
        }
        self.group_name: str = "sys.plugin.text"
        self.extra: list[str | dict[str, int]] = ["side", {"count": 2}]


def test_to_jsonable_kakao_value_preserves_public_attributes() -> None:
    param = FakeParam()

    serialized = to_jsonable_kakao_value(param)

    assert serialized == {
        "origin": "김치찌개",
        "value": {"value": "김치찌개", "resolved_value": "김치찌개"},
        "group_name": "sys.plugin.text",
        "extra": ["side", {"count": 2}],
    }


def test_dump_kakao_value_json_returns_utf8_json_string() -> None:
    param = FakeParam()

    dumped = dump_kakao_value_json(param)

    assert json.loads(dumped) == {
        "origin": "김치찌개",
        "value": {"value": "김치찌개", "resolved_value": "김치찌개"},
        "group_name": "sys.plugin.text",
        "extra": ["side", {"count": 2}],
    }
    assert "김치찌개" in dumped
