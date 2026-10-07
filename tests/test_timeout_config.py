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
    Config._validate()
