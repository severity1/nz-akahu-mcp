"""Tests for AkahuConfig: env loading, validation, auth headers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_loads_from_env(fake_env: None) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    cfg = AkahuConfig()
    assert cfg.app_token == "app_token_test"
    assert cfg.user_token == "user_token_test"
    assert cfg.base_url == "https://api.akahu.io/v1"
    assert cfg.read_only is True
    assert cfg.automation_bypass is False
    assert cfg.request_timeout == 5
    assert cfg.log_level == "INFO"


def test_base_url_trailing_slash_is_normalised(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    monkeypatch.setenv("AKAHU_BASE_URL", "https://api.akahu.io/v1/")
    assert AkahuConfig().base_url == "https://api.akahu.io/v1"


@pytest.mark.parametrize(
    ("base_url", "message"),
    [
        ("http://api.akahu.io/v1", "https"),
        ("https:///v1", "host"),
        ("https://api.akahu.io/v1?debug=true", "query"),
        ("https://api.akahu.io/v1#frag", "fragment"),
    ],
)
def test_rejects_unsafe_base_urls(
    monkeypatch: pytest.MonkeyPatch, fake_env: None, base_url: str, message: str
) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    monkeypatch.setenv("AKAHU_BASE_URL", base_url)
    with pytest.raises(ValidationError, match=message):
        AkahuConfig()


def test_is_configured_true_when_both_tokens_present(fake_env: None) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    assert AkahuConfig().is_configured is True


def test_is_configured_false_when_app_token_missing(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    monkeypatch.setenv("AKAHU_APP_TOKEN", "")
    assert AkahuConfig().is_configured is False


def test_is_configured_false_when_user_token_missing(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    monkeypatch.setenv("AKAHU_USER_TOKEN", "")
    assert AkahuConfig().is_configured is False


def test_auth_headers_contain_both_tokens(fake_env: None) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    cfg = AkahuConfig()
    headers = cfg.auth_headers
    assert headers["Authorization"] == "Bearer user_token_test"
    assert headers["X-Akahu-Id"] == "app_token_test"


def test_bypass_with_read_only_raises(monkeypatch: pytest.MonkeyPatch, fake_env: None) -> None:
    """Incoherent combination must fail loudly at startup, not silently ignore."""
    from nz_akahu_mcp.config import AkahuConfig

    monkeypatch.setenv("AKAHU_READ_ONLY", "true")
    monkeypatch.setenv("AKAHU_AUTOMATION_BYPASS", "true")
    with pytest.raises(ValidationError) as exc_info:
        AkahuConfig()
    assert "automation_bypass" in str(exc_info.value).lower()


def test_writable_env_loads(writable_env: None) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    cfg = AkahuConfig()
    assert cfg.read_only is False
    assert cfg.automation_bypass is False


def test_bypass_env_loads(bypass_env: None) -> None:
    from nz_akahu_mcp.config import AkahuConfig

    cfg = AkahuConfig()
    assert cfg.read_only is False
    assert cfg.automation_bypass is True
