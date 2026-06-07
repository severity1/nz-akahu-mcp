"""Environment-driven configuration for the Akahu MCP server.

See https://developers.akahu.nz/docs/personal-apps for the dual-header auth model:
- Authorization: Bearer <user_token>
- X-Akahu-Id: <app_token>
"""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AkahuConfig(BaseSettings):
    """All Akahu credentials and safety flags, sourced from env or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="AKAHU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_token: str = Field(default="", description="Akahu App Token (X-Akahu-Id header)")
    user_token: str = Field(default="", description="Akahu User Token (Authorization Bearer)")
    base_url: str = Field(default="https://api.akahu.io/v1")
    read_only: bool = Field(default=True, description="Refuse all write tools when true")
    automation_bypass: bool = Field(
        default=False,
        description="Skip elicit() for automatable writes (only when read_only is false)",
    )
    request_timeout: int = Field(default=10, ge=1, le=120)
    log_level: str = Field(default="INFO")

    @model_validator(mode="after")
    def _reject_incoherent_bypass(self) -> Self:
        """Reject AKAHU_READ_ONLY=true combined with AKAHU_AUTOMATION_BYPASS=true."""
        if self.automation_bypass and self.read_only:
            raise ValueError(
                "automation_bypass=true requires read_only=false. Either set "
                "AKAHU_READ_ONLY=false to enable writes, or "
                "AKAHU_AUTOMATION_BYPASS=false to silence this error."
            )
        return self

    @property
    def is_configured(self) -> bool:
        """True iff both tokens are present (non-empty)."""
        return bool(self.app_token) and bool(self.user_token)

    @property
    def auth_headers(self) -> dict[str, str]:
        """The two headers every Akahu request needs."""
        return {
            "Authorization": f"Bearer {self.user_token}",
            "X-Akahu-Id": self.app_token,
        }


class McpHttpConfig(BaseSettings):
    """HTTP transport settings for explicitly authenticated deployments."""

    model_config = SettingsConfigDict(
        env_prefix="AKAHU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    auth_mode: Literal["bearer", "oauth"] = Field(
        default="bearer",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_AUTH_MODE",
            "AKAHU_MCP_AUTH_MODE",
        ),
        description="Inbound MCP auth mode for HTTP clients: bearer or oauth",
    )
    bearer_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_BEARER_TOKEN",
            "AKAHU_MCP_BEARER_TOKEN",
        ),
        description="Required inbound MCP bearer token for HTTP clients",
    )
    host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_HTTP_HOST",
            "AKAHU_MCP_HTTP_HOST",
        ),
    )
    port: int = Field(
        default=8091,
        ge=1,
        le=65535,
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_HTTP_PORT",
            "AKAHU_MCP_HTTP_PORT",
        ),
    )
    path: str = Field(
        default="/mcp",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_HTTP_PATH",
            "AKAHU_MCP_HTTP_PATH",
        ),
    )

    @field_validator("auth_mode", mode="before")
    @classmethod
    def _normalise_auth_mode(cls, value: object) -> object:
        """Accept uppercase env values while preserving the Literal contract."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("bearer_token")
    @classmethod
    def _strip_bearer_token(cls, value: str) -> str:
        """Normalize bearer token input without requiring it for OAuth mode."""
        return value.strip()

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        """Require FastMCP's internal HTTP path to be absolute."""
        if not value.startswith("/"):
            raise ValueError("http path must start with /")
        return value

    @model_validator(mode="after")
    def _require_bearer_token(self) -> Self:
        """Require an explicit bearer token when HTTP runs in bearer mode."""
        if self.auth_mode == "bearer" and not self.bearer_token:
            raise ValueError("mcp bearer token is required for HTTP bearer mode")
        return self


class McpOAuthConfig(BaseSettings):
    """Google-backed OAuth proxy settings for the HTTP transport."""

    model_config = SettingsConfigDict(
        env_prefix="AKAHU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    google_client_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_GOOGLE_CLIENT_ID",
            "AKAHU_MCP_GOOGLE_CLIENT_ID",
        ),
        description="Google OAuth client ID used by the inbound OAuth proxy",
    )
    google_client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_GOOGLE_CLIENT_SECRET",
            "AKAHU_MCP_GOOGLE_CLIENT_SECRET",
        ),
        description="Google OAuth client secret used by the inbound OAuth proxy",
    )
    public_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_PUBLIC_BASE_URL",
            "AKAHU_MCP_PUBLIC_BASE_URL",
        ),
        description="Public URL prefix where OAuth endpoints are reachable",
    )
    allowed_users: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_ALLOWED_USERS",
            "AKAHU_MCP_ALLOWED_USERS",
        ),
        description="Comma-separated allowlist of Google email addresses",
    )
    allowed_domains: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NZ_AKAHU_MCP_ALLOWED_DOMAINS",
            "AKAHU_MCP_ALLOWED_DOMAINS",
        ),
        description="Comma-separated allowlist of Google email domains",
    )

    @field_validator("google_client_id", "public_base_url", "allowed_users", "allowed_domains")
    @classmethod
    def _strip_string(cls, value: str) -> str:
        """Normalize whitespace-heavy env values."""
        return value.strip()

    @field_validator("public_base_url")
    @classmethod
    def _validate_public_base_url(cls, value: str) -> str:
        """Require the externally reachable OAuth URL prefix to be HTTPS."""
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("oauth public base url must use https")
        if not parsed.netloc:
            raise ValueError("oauth public base url must include a host")
        if parsed.query:
            raise ValueError("oauth public base url must not include a query string")
        if parsed.fragment:
            raise ValueError("oauth public base url must not include a fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _require_oauth_fields(self) -> Self:
        """Reject OAuth startup without Google credentials and an allowlist."""
        if not self.google_client_id:
            raise ValueError("google oauth client id is required for HTTP oauth mode")
        if not self.google_client_secret.get_secret_value().strip():
            raise ValueError("google oauth client secret is required for HTTP oauth mode")
        if not self.public_base_url:
            raise ValueError("oauth public base url is required for HTTP oauth mode")
        for email in self.allowed_user_set:
            if "@" not in email or email.startswith("@") or email.endswith("@"):
                raise ValueError("oauth allowed users must be email addresses")
        for domain in self.allowed_domain_set:
            if not domain or "@" in domain or "/" in domain:
                raise ValueError("oauth allowed domains must be bare domains")
        if not self.allowed_user_set and not self.allowed_domain_set:
            raise ValueError(
                "oauth allowlist is required for HTTP oauth mode. Set allowed users "
                "or allowed domains."
            )
        return self

    @property
    def allowed_user_set(self) -> frozenset[str]:
        """Normalized allowed Google account email addresses."""
        return frozenset(_split_csv_lower(self.allowed_users))

    @property
    def allowed_domain_set(self) -> frozenset[str]:
        """Normalized allowed Google account domains."""
        return frozenset(
            _normalise_domain(value) for value in _split_csv_lower(self.allowed_domains)
        )

    @property
    def google_redirect_uri(self) -> str:
        """Google Cloud Console redirect URI for the OAuth proxy callback."""
        return f"{self.public_base_url}/auth/callback"


def _split_csv_lower(value: str) -> tuple[str, ...]:
    """Split comma-separated config into lowercase non-empty entries."""
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def _normalise_domain(value: str) -> str:
    """Normalize email-domain allowlist entries."""
    return value.removeprefix("@")
