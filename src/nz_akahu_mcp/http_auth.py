"""Inbound authentication for Streamable HTTP MCP deployments."""

from __future__ import annotations

import hmac
from collections.abc import Iterable, Mapping
from typing import cast
from urllib.parse import urlparse

from fastmcp.server.auth import AccessToken as FastMCPAccessToken
from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.protocols import AsyncKeyValue
from mcp.server.auth.provider import AccessToken as McpAccessToken
from mcp.server.auth.provider import AuthorizationCode, TokenError
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.routing import Route

GOOGLE_OAUTH_SCOPES = ["openid", "email", "profile"]


class StaticBearerAuthProvider(AuthProvider):
    """Authenticate HTTP MCP requests against one configured bearer token."""

    def __init__(self, bearer_token: str) -> None:
        super().__init__()
        self._bearer_token = bearer_token

    async def verify_token(self, token: str) -> FastMCPAccessToken | None:
        """Return access metadata only when the supplied bearer token matches."""
        if hmac.compare_digest(token, self._bearer_token):
            return FastMCPAccessToken(
                token=token,
                client_id="nz-akahu-mcp-http",
                scopes=[],
            )
        return None


class AllowlistedGoogleOAuthProvider(GoogleProvider):
    """Google OAuth proxy that only accepts verified allowlisted accounts."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str,
        allowed_users: Iterable[str],
        allowed_domains: Iterable[str],
        client_storage: AsyncKeyValue | None = None,
    ) -> None:
        self._allowed_users = frozenset(_normalise_email(value) for value in allowed_users)
        self._allowed_domains = frozenset(
            _normalise_domain(value) for value in allowed_domains
        )
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            resource_base_url=base_url,
            issuer_url=base_url,
            required_scopes=GOOGLE_OAUTH_SCOPES,
            valid_scopes=GOOGLE_OAUTH_SCOPES,
            client_storage=client_storage,
        )

    async def load_access_token(self, token: str) -> FastMCPAccessToken | None:
        """Return FastMCP-issued access only for an allowlisted Google email."""
        access = cast(
            FastMCPAccessToken | None,
            await super().load_access_token(token),
        )
        if access is None:
            return None
        if self._is_access_allowed(access):
            return access
        return None

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Issue connector tokens only when the Google account is allowlisted."""
        oauth_token = await super().exchange_authorization_code(client, authorization_code)
        if await self.load_access_token(oauth_token.access_token) is None:
            raise TokenError("invalid_grant", "Google account is not allowed")
        return oauth_token

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Expose the path-aware authorization-server metadata alias."""
        routes = super().get_routes(mcp_path)
        issuer_path = urlparse(str(self.issuer_url)).path.rstrip("/")
        alias_path = f"/.well-known/oauth-authorization-server{issuer_path}"
        if issuer_path and not any(route.path == alias_path for route in routes):
            for route in routes:
                if route.path == "/.well-known/oauth-authorization-server":
                    routes.append(
                        Route(
                            path=alias_path,
                            endpoint=route.endpoint,
                            methods=route.methods,
                            name=route.name,
                            include_in_schema=route.include_in_schema,
                        )
                    )
                    break
        return routes

    def _is_access_allowed(self, access: McpAccessToken) -> bool:
        claims = _access_claims(access)
        email_claim = claims.get("email")
        if not isinstance(email_claim, str):
            return False
        if not _claim_is_true(claims.get("email_verified")):
            return False

        email = _normalise_email(email_claim)
        domain = email.rsplit("@", maxsplit=1)[-1]
        return email in self._allowed_users or domain in self._allowed_domains


def _normalise_email(value: str) -> str:
    """Normalize Google email claims for allowlist comparison."""
    return value.strip().lower()


def _normalise_domain(value: str) -> str:
    """Normalize Google hosted-domain allowlist entries."""
    return value.strip().lower().removeprefix("@")


def _claim_is_true(value: object) -> bool:
    """Google tokeninfo may return boolean-like values as strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return False


def _access_claims(access: McpAccessToken) -> Mapping[str, object]:
    """Return FastMCP token claims when present on the SDK access token."""
    claims = getattr(access, "claims", {})
    if isinstance(claims, Mapping):
        return claims
    return {}
