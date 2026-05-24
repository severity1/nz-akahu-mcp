"""Environment-driven configuration for the Akahu MCP server.

See https://developers.akahu.nz/docs/personal-apps for the dual-header auth model:
- Authorization: Bearer <user_token>
- X-Akahu-Id: <app_token>
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator
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
        """A bypass flag with read-only on is incoherent; fail loudly."""
        if self.automation_bypass and self.read_only:
            raise ValueError(
                "automation_bypass=true requires read_only=false. The combination "
                "AKAHU_READ_ONLY=true with AKAHU_AUTOMATION_BYPASS=true is incoherent: "
                "writes are disabled, so there is nothing to bypass. Either set "
                "AKAHU_READ_ONLY=false to enable writes, or AKAHU_AUTOMATION_BYPASS=false "
                "to silence this error."
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
