from types import SimpleNamespace

from keycloak.exceptions import (
    KeycloakAuthenticationError,
    KeycloakGetError,
)

from app.services import auth_service


def test_keycloak_user_exists_returns_true_when_admin_lookup_succeeds(
    monkeypatch,
) -> None:
    admin_client = SimpleNamespace(get_user=lambda *_: {"id": "keycloak-sub-1"})
    monkeypatch.setattr(auth_service, "get_keycloak_admin_client", lambda: admin_client)

    assert auth_service.keycloak_user_exists("keycloak-sub-1") is True


def test_keycloak_user_exists_returns_false_on_not_found(monkeypatch) -> None:
    def raise_not_found(*_: object) -> dict[str, object]:
        raise KeycloakGetError("not found", response_code=404)

    admin_client = SimpleNamespace(get_user=raise_not_found)
    monkeypatch.setattr(auth_service, "get_keycloak_admin_client", lambda: admin_client)

    assert auth_service.keycloak_user_exists("keycloak-sub-1") is False


def test_keycloak_user_exists_returns_none_on_forbidden(monkeypatch) -> None:
    def raise_forbidden(*_: object) -> dict[str, object]:
        raise KeycloakGetError("forbidden", response_code=403)

    admin_client = SimpleNamespace(get_user=raise_forbidden)
    monkeypatch.setattr(auth_service, "get_keycloak_admin_client", lambda: admin_client)

    assert auth_service.keycloak_user_exists("keycloak-sub-1") is None


def test_keycloak_user_exists_returns_none_on_authentication_failure(
    monkeypatch,
) -> None:
    def raise_authentication(*_: object) -> dict[str, object]:
        raise KeycloakAuthenticationError("unauthorized", response_code=401)

    admin_client = SimpleNamespace(get_user=raise_authentication)
    monkeypatch.setattr(auth_service, "get_keycloak_admin_client", lambda: admin_client)

    assert auth_service.keycloak_user_exists("keycloak-sub-1") is None


def test_get_keycloak_admin_client_reuses_default_client_credentials(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_keycloak_admin(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(auth_service, "KeycloakAdmin", fake_keycloak_admin)

    auth_service.get_keycloak_admin_client()

    assert captured["client_id"] == auth_service.Config.KC_CLIENT_ID
    assert captured["client_secret_key"] == auth_service.Config.KC_CLIENT_SECRET
