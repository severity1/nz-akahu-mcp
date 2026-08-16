"""Tests for AkahuConfig: env loading, validation, auth headers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

OAUTH_ENV_VARS = (
    "NZ_AKAHU_MCP_GOOGLE_CLIENT_ID",
    "AKAHU_MCP_GOOGLE_CLIENT_ID",
    "NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET",
    "AKAHU_MCP_GOOGLE_CLIENT_SECRET",
    "NZ_AKAHU_MCP_PUBLIC_BASE_URL",
    "AKAHU_MCP_PUBLIC_BASE_URL",
    "NZ_AKAHU_MCP_ALLOWED_USERS",
    "AKAHU_MCP_ALLOWED_USERS",
    "NZ_AKAHU_MCP_ALLOWED_DOMAINS",
    "AKAHU_MCP_ALLOWED_DOMAINS",
)


@pytest.fixture
def clean_oauth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove OAuth env vars that could be present on a developer host."""
    for key in OAUTH_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    yield


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
    from pydantic import ValidationError

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


def test_http_config_loads_nz_prefixed_env(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.setenv("NZ_AKAHU_MCP_BEARER_TOKEN", "http_token_test")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_PORT", "8091")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_PATH", "/mcp")

    cfg = McpHttpConfig()
    assert cfg.auth_mode == "bearer"
    assert cfg.bearer_token == "http_token_test"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8091
    assert cfg.path == "/mcp"


def test_http_config_loads_akahu_prefixed_bearer_alias(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.delenv("NZ_AKAHU_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AKAHU_MCP_BEARER_TOKEN", "http_token_test")

    assert McpHttpConfig().bearer_token == "http_token_test"


def test_http_config_oauth_mode_does_not_require_bearer(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.delenv("NZ_AKAHU_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AKAHU_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AKAHU_MCP_AUTH_MODE", "OAUTH")

    cfg = McpHttpConfig()
    assert cfg.auth_mode == "oauth"
    assert cfg.bearer_token == ""


def test_http_config_ignores_unprefixed_process_path(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.setenv("PATH", "/not/the/mcp/path")
    monkeypatch.setenv("AKAHU_MCP_AUTH_MODE", "oauth")

    assert McpHttpConfig().path == "/mcp"


def test_http_config_rejects_non_string_auth_mode(fake_env: None) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    with pytest.raises(ValidationError, match="auth_mode"):
        McpHttpConfig(auth_mode=b"oauth")


def test_http_config_requires_bearer_token(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.delenv("NZ_AKAHU_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AKAHU_MCP_BEARER_TOKEN", raising=False)

    with pytest.raises(ValidationError, match="bearer token"):
        McpHttpConfig()


def test_http_config_rejects_relative_path(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig

    monkeypatch.setenv("NZ_AKAHU_MCP_BEARER_TOKEN", "http_token_test")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_PATH", "mcp")

    with pytest.raises(ValidationError, match="http path"):
        McpHttpConfig()


def test_oauth_config_loads_nz_prefixed_env(
    monkeypatch: pytest.MonkeyPatch, clean_oauth_env: None
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    monkeypatch.setenv(
        "NZ_AKAHU_MCP_GOOGLE_CLIENT_ID",
        "google-client.apps.googleusercontent.com",
    )
    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv(
        "NZ_AKAHU_MCP_PUBLIC_BASE_URL",
        "https://mcp.example.com/akahu-mcp/",
    )
    monkeypatch.setenv(
        "NZ_AKAHU_MCP_ALLOWED_USERS",
        " Owner@example.com , Other@example.com ",
    )
    monkeypatch.setenv("NZ_AKAHU_MCP_ALLOWED_DOMAINS", " Example.ORG , @Example.NET ")

    cfg = McpOAuthConfig()

    assert cfg.google_client_id == "google-client.apps.googleusercontent.com"
    assert cfg.google_client_secret.get_secret_value() == "google-secret"
    assert cfg.public_base_url == "https://mcp.example.com/akahu-mcp"
    assert cfg.allowed_user_set == frozenset({"owner@example.com", "other@example.com"})
    assert cfg.allowed_domain_set == frozenset({"example.org", "example.net"})
    assert cfg.google_redirect_uri == "https://mcp.example.com/akahu-mcp/auth/callback"
    assert "google-secret" not in repr(cfg)


def test_oauth_config_loads_akahu_prefixed_aliases(
    monkeypatch: pytest.MonkeyPatch, clean_oauth_env: None
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    monkeypatch.setenv("AKAHU_MCP_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("AKAHU_MCP_PUBLIC_BASE_URL", "https://example.com/akahu")
    monkeypatch.setenv("AKAHU_MCP_ALLOWED_USERS", "owner@example.com")

    cfg = McpOAuthConfig()
    assert cfg.google_client_id == "google-client"
    assert cfg.allowed_user_set == frozenset({"owner@example.com"})


@pytest.mark.parametrize(
    ("missing_key", "message"),
    [
        ("NZ_AKAHU_MCP_GOOGLE_CLIENT_ID", "client id"),
        ("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "client secret"),
        ("NZ_AKAHU_MCP_PUBLIC_BASE_URL", "public base url"),
    ],
)
def test_oauth_config_requires_core_fields(
    monkeypatch: pytest.MonkeyPatch,
    clean_oauth_env: None,
    missing_key: str,
    message: str,
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    values = {
        "NZ_AKAHU_MCP_GOOGLE_CLIENT_ID": "google-client",
        "NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET": "google-secret",
        "NZ_AKAHU_MCP_PUBLIC_BASE_URL": "https://mcp.example.com/akahu-mcp",
        "NZ_AKAHU_MCP_ALLOWED_USERS": "owner@example.com",
    }
    values[missing_key] = ""
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError, match=message):
        McpOAuthConfig()


def test_oauth_config_requires_allowlist(
    monkeypatch: pytest.MonkeyPatch, clean_oauth_env: None
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("NZ_AKAHU_MCP_PUBLIC_BASE_URL", "https://mcp.example.com/akahu-mcp")

    with pytest.raises(ValidationError, match="allowlist"):
        McpOAuthConfig()


@pytest.mark.parametrize(
    ("public_base_url", "message"),
    [
        ("http://mcp.example.com/akahu-mcp", "https"),
        ("https:///akahu-mcp", "host"),
        ("https://mcp.example.com/akahu-mcp?debug=true", "query"),
        ("https://mcp.example.com/akahu-mcp#frag", "fragment"),
    ],
)
def test_oauth_config_rejects_bad_public_base_urls(
    monkeypatch: pytest.MonkeyPatch,
    clean_oauth_env: None,
    public_base_url: str,
    message: str,
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("NZ_AKAHU_MCP_PUBLIC_BASE_URL", public_base_url)
    monkeypatch.setenv("NZ_AKAHU_MCP_ALLOWED_USERS", "owner@example.com")

    with pytest.raises(ValidationError, match=message):
        McpOAuthConfig()


@pytest.mark.parametrize(
    ("allowed_users", "allowed_domains", "message"),
    [
        ("not-an-email", "", "email addresses"),
        ("", "https://example.com", "bare domains"),
        ("", "@", "bare domains"),
    ],
)
def test_oauth_config_rejects_bad_allowlist_entries(
    monkeypatch: pytest.MonkeyPatch,
    clean_oauth_env: None,
    allowed_users: str,
    allowed_domains: str,
    message: str,
) -> None:
    from nz_akahu_mcp.config import McpOAuthConfig

    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("NZ_AKAHU_MCP_PUBLIC_BASE_URL", "https://mcp.example.com/akahu-mcp")
    monkeypatch.setenv("NZ_AKAHU_MCP_ALLOWED_USERS", allowed_users)
    monkeypatch.setenv("NZ_AKAHU_MCP_ALLOWED_DOMAINS", allowed_domains)

    with pytest.raises(ValidationError, match=message):
        McpOAuthConfig()
