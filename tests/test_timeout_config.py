import pytest

from app.config import Config


@pytest.mark.parametrize("timeout", [0.0, -1.0, 5.0, float("inf"), float("nan")])
def test_config_rejects_invalid_request_budget(
    monkeypatch: pytest.MonkeyPatch, timeout: float
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", timeout)
    with pytest.raises(ValueError, match="KAKAO_REQUEST_TIMEOUT_SECONDS"):
        Config._validate()


@pytest.mark.parametrize("timeout", [0.1, 4.0, 4.9])
def test_config_accepts_request_budget(
    monkeypatch: pytest.MonkeyPatch, timeout: float
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", timeout)
    monkeypatch.setattr(Config, "DOWNSTREAM_HTTP_TIMEOUT_SECONDS", timeout / 2)
    monkeypatch.setattr(Config, "DOWNSTREAM_HTTP_CONNECT_TIMEOUT_SECONDS", timeout / 4)
    Config._validate()


@pytest.mark.parametrize(
    "setting",
    ["DOWNSTREAM_HTTP_TIMEOUT_SECONDS", "DOWNSTREAM_HTTP_CONNECT_TIMEOUT_SECONDS"],
)
@pytest.mark.parametrize("timeout", [0.0, -1.0, 4.0, 5.0, float("inf"), float("nan")])
def test_config_rejects_invalid_downstream_timeout(
    monkeypatch: pytest.MonkeyPatch, setting: str, timeout: float
) -> None:
    monkeypatch.setattr(Config, "KAKAO_REQUEST_TIMEOUT_SECONDS", 4.0)
    monkeypatch.setattr(Config, setting, timeout)
    with pytest.raises(ValueError, match=setting):
        Config._validate()


def test_config_starts_without_issue_link_secret_and_logs_error_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(Config, "debug", False)
    monkeypatch.setattr(Config, "KC_CLIENT_SECRET", "kc-secret")
    monkeypatch.setattr(Config, "RELAY_CLIENT_SECRETS", "relay-secret")
    monkeypatch.setattr(Config, "RELAY_ISSUE_LINK_SECRET", "")
    Config._validate()  # 기동을 막지 않는다
    errors = [r for r in caplog.records if "RELAY_ISSUE_LINK_SECRET" in r.getMessage()]
    assert len(errors) == 1
    assert errors[0].levelname == "ERROR"
