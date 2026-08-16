"""Tests for the root server: composition, namespaces, startup banner."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastmcp.server.auth import AccessToken
from key_value.aio.stores.memory import MemoryStore
from starlette.testclient import TestClient


def _oauth_config() -> Any:
    from nz_akahu_mcp.config import McpOAuthConfig

    return McpOAuthConfig(
        google_client_id="google-client.apps.googleusercontent.com",
        google_client_secret="google-secret",
        public_base_url="https://mcp.example.com/akahu-mcp",
        allowed_users="owner@example.com",
    )


async def test_root_server_exposes_all_14_tools(fake_env: None) -> None:
    from nz_akahu_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        # accounts (6)
        "acct_list_accounts",
        "acct_get_account",
        "acct_get_account_balance",
        "acct_get_pending_transactions",
        "acct_refresh_all_accounts",
        "acct_refresh_account",
        # transactions (6)
        "txn_get_transactions",
        "txn_get_transaction",
        "txn_get_transactions_by_ids",
        "txn_get_pending_transactions",
        "txn_search_transactions",
        "txn_report_transaction_issue",
        # identity (2) -- /categories, /parties, /identity/{id}/verify-name are app-scoped
        "id_get_me",
        "id_verify_name",
    }
    assert names == expected


async def test_http_server_exposes_all_14_tools_with_auth(fake_env: None) -> None:
    from nz_akahu_mcp.config import McpHttpConfig
    from nz_akahu_mcp.http_auth import StaticBearerAuthProvider
    from nz_akahu_mcp.server import build_http_server

    mcp = build_http_server(McpHttpConfig(bearer_token="http_token_test"))
    tools = await mcp.list_tools()
    assert len(tools) == 14
    assert isinstance(mcp.auth, StaticBearerAuthProvider)


async def test_http_server_exposes_all_14_tools_with_oauth(fake_env: None) -> None:
    from nz_akahu_mcp.config import McpHttpConfig
    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider
    from nz_akahu_mcp.server import build_http_server

    mcp = build_http_server(
        McpHttpConfig(auth_mode="oauth"),
        _oauth_config(),
        oauth_client_storage=MemoryStore(),
    )

    tools = await mcp.list_tools()
    assert len(tools) == 14
    assert isinstance(mcp.auth, AllowlistedGoogleOAuthProvider)


def test_http_server_oauth_mode_loads_oauth_env(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp.config import McpHttpConfig
    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider
    from nz_akahu_mcp.server import build_http_server

    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv(
        "NZ_AKAHU_MCP_PUBLIC_BASE_URL",
        "https://mcp.example.com/akahu-mcp",
    )
    monkeypatch.setenv("NZ_AKAHU_MCP_ALLOWED_USERS", "owner@example.com")

    mcp = build_http_server(
        McpHttpConfig(auth_mode="oauth"),
        oauth_client_storage=MemoryStore(),
    )

    assert isinstance(mcp.auth, AllowlistedGoogleOAuthProvider)


async def test_http_bearer_auth_provider_accepts_only_expected_token() -> None:
    from nz_akahu_mcp.http_auth import StaticBearerAuthProvider

    provider = StaticBearerAuthProvider("http_token_test")
    assert await provider.verify_token("wrong_token") is None

    access = await provider.verify_token("http_token_test")
    assert access is not None
    assert access.client_id == "nz-akahu-mcp-http"
    assert access.scopes == []


def test_oauth_provider_allowlist_accepts_users_and_domains() -> None:
    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://mcp.example.com/akahu-mcp",
        allowed_users=["Owner@Example.com"],
        allowed_domains=["Example.org"],
        client_storage=MemoryStore(),
    )

    assert provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": "owner@example.com", "email_verified": True},
        )
    )
    assert provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": "person@example.org", "email_verified": "true"},
        )
    )


def test_oauth_provider_allowlist_rejects_unverified_or_unknown_email() -> None:
    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://mcp.example.com/akahu-mcp",
        allowed_users=["owner@example.com"],
        allowed_domains=["example.org"],
        client_storage=MemoryStore(),
    )

    assert not provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": "owner@example.com", "email_verified": False},
        )
    )
    assert not provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": "owner@example.com", "email_verified": "false"},
        )
    )
    assert not provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": 123, "email_verified": True},
        )
    )
    assert not provider._is_access_allowed(
        AccessToken(
            token="token",
            client_id="google-user",
            scopes=[],
            claims={"email": "stranger@example.net", "email_verified": object()},
        )
    )


async def test_oauth_provider_load_access_token_filters_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider

    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://mcp.example.com/akahu-mcp",
        allowed_users=["owner@example.com"],
        allowed_domains=[],
        client_storage=MemoryStore(),
    )
    allowed = AccessToken(
        token="token",
        client_id="google-user",
        scopes=[],
        claims={"email": "owner@example.com", "email_verified": True},
    )
    denied = AccessToken(
        token="token",
        client_id="google-user",
        scopes=[],
        claims={"email": "stranger@example.com", "email_verified": True},
    )

    async def fake_allowed(self: object, token: str) -> AccessToken | None:
        return allowed

    async def fake_denied(self: object, token: str) -> AccessToken | None:
        return denied

    async def fake_missing(self: object, token: str) -> AccessToken | None:
        return None

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_allowed)
    assert await provider.load_access_token("allowed-token") == allowed

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_denied)
    assert await provider.load_access_token("denied-token") is None

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_missing)
    assert await provider.load_access_token("missing-token") is None


async def test_oauth_provider_exchange_authorization_code_enforces_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider
    from mcp.server.auth.provider import TokenError
    from mcp.shared.auth import OAuthToken

    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://mcp.example.com/akahu-mcp",
        allowed_users=["owner@example.com"],
        allowed_domains=[],
        client_storage=MemoryStore(),
    )
    access = AccessToken(
        token="issued-token",
        client_id="google-user",
        scopes=[],
        claims={"email": "owner@example.com", "email_verified": True},
    )

    async def fake_exchange(
        self: object,
        client: object,
        authorization_code: object,
    ) -> OAuthToken:
        return OAuthToken(access_token="issued-token")

    async def fake_allowed(self: object, token: str) -> AccessToken | None:
        return access

    async def fake_denied(self: object, token: str) -> AccessToken | None:
        return None

    monkeypatch.setattr(GoogleProvider, "exchange_authorization_code", fake_exchange)
    monkeypatch.setattr(AllowlistedGoogleOAuthProvider, "load_access_token", fake_allowed)
    oauth_token = await provider.exchange_authorization_code(object(), object())
    assert oauth_token.access_token == "issued-token"

    monkeypatch.setattr(AllowlistedGoogleOAuthProvider, "load_access_token", fake_denied)
    with pytest.raises(TokenError, match="not allowed"):
        await provider.exchange_authorization_code(object(), object())


def test_http_app_rejects_missing_bearer(fake_env: None) -> None:
    from nz_akahu_mcp.config import McpHttpConfig
    from nz_akahu_mcp.server import build_http_server

    cfg = McpHttpConfig(bearer_token="http_token_test")
    app = build_http_server(cfg).http_app(
        path=cfg.path,
        transport="streamable-http",
    )

    with TestClient(app) as client:
        response = client.post(cfg.path, json={})

    assert response.status_code == 401


def test_oauth_http_app_exposes_metadata_and_rejects_missing_token(fake_env: None) -> None:
    from nz_akahu_mcp.config import McpHttpConfig
    from nz_akahu_mcp.server import build_http_server

    cfg = McpHttpConfig(auth_mode="oauth")
    app = build_http_server(
        cfg,
        _oauth_config(),
        oauth_client_storage=MemoryStore(),
    ).http_app(
        path=cfg.path,
        transport="streamable-http",
    )

    with TestClient(app) as client:
        protected = client.get(
            "/.well-known/oauth-protected-resource/akahu-mcp/mcp"
        )
        authorization = client.get(
            "/.well-known/oauth-authorization-server/akahu-mcp"
        )
        unauthenticated = client.post(cfg.path, json={})

    protected_metadata = protected.json()
    authorization_metadata = authorization.json()

    assert protected.status_code == 200
    assert protected_metadata["resource"] == "https://mcp.example.com/akahu-mcp/mcp"
    assert protected_metadata["authorization_servers"] == [
        "https://mcp.example.com/akahu-mcp"
    ]
    assert authorization.status_code == 200
    assert authorization_metadata["issuer"] == "https://mcp.example.com/akahu-mcp"
    assert authorization_metadata["authorization_endpoint"] == (
        "https://mcp.example.com/akahu-mcp/authorize"
    )
    assert authorization_metadata["token_endpoint"] == (
        "https://mcp.example.com/akahu-mcp/token"
    )
    assert authorization_metadata["registration_endpoint"] == (
        "https://mcp.example.com/akahu-mcp/register"
    )
    assert unauthenticated.status_code == 401


def test_oauth_provider_without_path_does_not_add_path_aware_alias() -> None:
    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://example.com",
        allowed_users=["owner@example.com"],
        allowed_domains=[],
        client_storage=MemoryStore(),
    )

    route_paths = {route.path for route in provider.get_routes("/mcp")}
    assert "/.well-known/oauth-authorization-server" in route_paths
    assert "/.well-known/oauth-authorization-server/" not in route_paths


def test_oauth_provider_keeps_routes_when_base_metadata_route_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastmcp.server.auth.providers.google import GoogleProvider
    from starlette.responses import Response
    from starlette.routing import Route

    from nz_akahu_mcp.http_auth import AllowlistedGoogleOAuthProvider

    async def endpoint(request: object) -> Response:
        return Response()

    def fake_routes(self: object, mcp_path: str | None = None) -> list[Route]:
        return [Route("/other", endpoint=endpoint)]

    monkeypatch.setattr(GoogleProvider, "get_routes", fake_routes)
    provider = AllowlistedGoogleOAuthProvider(
        client_id="google-client",
        client_secret="google-secret",
        base_url="https://mcp.example.com/akahu-mcp",
        allowed_users=["owner@example.com"],
        allowed_domains=[],
        client_storage=MemoryStore(),
    )

    route_paths = [route.path for route in provider.get_routes("/mcp")]
    assert route_paths == ["/other"]


def test_access_claims_rejects_non_mapping_claims() -> None:
    from nz_akahu_mcp.http_auth import _access_claims

    token = type("Token", (), {"claims": ["not", "a", "mapping"]})()

    assert _access_claims(token) == {}


async def test_composed_plugin_names_fit_kiro_limit(fake_env: None) -> None:
    """Guard: marketplace-plugin-composed names must stay within Kiro's 64-char cap."""
    from nz_akahu_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    prefix = "mcp__plugin_nz-akahu-mcp_akahu__"
    for t in tools:
        composed = prefix + t.name
        assert len(composed) <= 64, f"{composed} is {len(composed)} chars"


def test_startup_banner_when_bypass_off(
    writable_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "all writes require confirmation" in blob.lower()


def test_startup_banner_when_bypass_on(
    bypass_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.WARNING, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "automation bypass enabled" in blob.lower()
    assert "refresh_all_accounts" in blob
    assert "refresh_account" in blob


def test_startup_banner_when_readonly(
    fake_env: None, caplog: pytest.LogCaptureFixture
) -> None:
    from nz_akahu_mcp.server import log_startup_banner

    with caplog.at_level(logging.INFO, logger="nz_akahu_mcp.server"):
        log_startup_banner()
    blob = "\n".join(r.message for r in caplog.records)
    assert "read-only" in blob.lower()


def test_configure_logging_suppresses_sensitive_http_client_logs() -> None:
    from nz_akahu_mcp.server import configure_logging

    old_levels = {
        logger_name: logging.getLogger(logger_name).level
        for logger_name in ("httpx", "httpcore", "uvicorn.access")
    }
    try:
        for logger_name in old_levels:
            logging.getLogger(logger_name).setLevel(logging.NOTSET)

        configure_logging("INFO")

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
    finally:
        for logger_name, level in old_levels.items():
            logging.getLogger(logger_name).setLevel(level)


def test_main_constructs_and_runs(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() must build the server and call .run(); we verify the call site."""
    from nz_akahu_mcp import server

    called: dict[str, bool] = {"run": False}

    def fake_run(self: object) -> None:
        called["run"] = True

    monkeypatch.setattr(server.FastMCP, "run", fake_run)
    server.main()
    assert called["run"] is True


def test_http_main_constructs_and_runs(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """http_main() must build the auth server and use Streamable HTTP."""
    from nz_akahu_mcp import server

    monkeypatch.setenv("NZ_AKAHU_MCP_BEARER_TOKEN", "http_token_test")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_PORT", "8091")
    monkeypatch.setenv("NZ_AKAHU_MCP_HTTP_PATH", "/mcp")

    called: dict[str, object] = {}

    def fake_run(
        self: object,
        transport: str | None = None,
        show_banner: bool | None = None,
        **transport_kwargs: object,
    ) -> None:
        called["transport"] = transport
        called["show_banner"] = show_banner
        called["transport_kwargs"] = transport_kwargs

    monkeypatch.setattr(server.FastMCP, "run", fake_run)
    server.http_main()

    assert called == {
        "transport": "streamable-http",
        "show_banner": None,
        "transport_kwargs": {
            "host": "127.0.0.1",
            "port": 8091,
            "path": "/mcp",
            "uvicorn_config": {"access_log": False},
        },
    }
