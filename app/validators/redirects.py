"""Helpers for validating post-login redirect paths."""

from __future__ import annotations

from urllib.parse import urlsplit


def is_safe_relative_path(path: str) -> bool:
    """Return whether the path is a safe relative redirect target."""
    if not path.startswith("/"):
        return False
    if path.startswith("//"):
        return False
    if "\\" in path:
        return False

    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        return False
    return True


def normalize_optional_relative_path(path: str | None) -> str | None:
    """Normalize an optional redirect path and reject unsafe values."""
    if path is None:
        return None

    normalized = path.strip()
    if not normalized:
        return None
    if not is_safe_relative_path(normalized):
        raise ValueError(
            "LOGIN_REDIRECT_AFTER must be a safe relative path starting with '/'."
        )
    return normalized
