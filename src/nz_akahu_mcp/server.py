"""Root FastMCP server. Mounts sub-servers and runs over stdio."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from key_value.aio.protocols import AsyncKeyValue

from nz_akahu_mcp.config import AkahuConfig, McpHttpConfig, McpOAuthConfig
from nz_akahu_mcp.http_auth import (
    AllowlistedGoogleOAuthProvider,
    StaticBearerAuthProvider,
)
from nz_akahu_mcp.safety import bypass_eligible_tools
from nz_akahu_mcp.tools import accounts, identity, transactions

logger = logging.getLogger(__name__)
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_SENSITIVE_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "uvicorn.access")


def build_server(*, auth: AuthProvider | None = None) -> FastMCP[Any]:
    """Construct the root FastMCP server with all sub-servers mounted."""
    mcp: FastMCP[Any] = FastMCP("nz-akahu-mcp", auth=auth)
    mcp.mount(accounts.server, namespace="acct")
    mcp.mount(transactions.server, namespace="txn")
    mcp.mount(identity.server, namespace="id")
    return mcp


def build_http_server(
    http_cfg: McpHttpConfig,
    oauth_cfg: McpOAuthConfig | None = None,
    oauth_client_storage: AsyncKeyValue | None = None,
) -> FastMCP[Any]:
    """Construct the root server with configured inbound HTTP auth."""
    if http_cfg.auth_mode == "oauth":
        if oauth_cfg is None:
            oauth_cfg = McpOAuthConfig()
        auth: AuthProvider = AllowlistedGoogleOAuthProvider(
            client_id=oauth_cfg.google_client_id,
            client_secret=oauth_cfg.google_client_secret.get_secret_value(),
            base_url=oauth_cfg.public_base_url,
            allowed_users=oauth_cfg.allowed_user_set,
            allowed_domains=oauth_cfg.allowed_domain_set,
            client_storage=oauth_client_storage,
        )
        return build_server(auth=auth)
    return build_server(auth=StaticBearerAuthProvider(http_cfg.bearer_token))


def log_startup_banner() -> None:
    """Emit a banner describing the current safety posture."""
    cfg = AkahuConfig()
    if cfg.read_only:
        logger.info(
            "nz-akahu-mcp starting in READ-ONLY mode. All write tools will refuse "
            "until AKAHU_READ_ONLY=false."
        )
        return
    if cfg.automation_bypass:
        eligible = bypass_eligible_tools()
        logger.warning(
            "Automation bypass ENABLED. The following tools will skip the "
            "confirmation prompt: %s. All other writes still require "
            "confirmation. Disable by removing AKAHU_AUTOMATION_BYPASS from .env.",
            ", ".join(eligible),
        )
        return
    logger.info(
        "nz-akahu-mcp starting in WRITE mode. All writes require confirmation "
        "through Claude."
    )


def configure_logging(log_level: str) -> None:
    """Configure application logging without leaking bearer tokens from HTTP clients."""
    logging.basicConfig(level=log_level, format=_LOG_FORMAT)
    for logger_name in _SENSITIVE_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def main() -> None:
    """Entry point used by the `nz-akahu-mcp` console script."""
    configure_logging(AkahuConfig().log_level)
    log_startup_banner()
    build_server().run()


def http_main() -> None:
    """Entry point used by the `nz-akahu-mcp-http` console script."""
    akahu_cfg = AkahuConfig()
    http_cfg = McpHttpConfig()
    configure_logging(akahu_cfg.log_level)
    log_startup_banner()
    logger.info(
        "nz-akahu-mcp HTTP starting on %s:%s%s with %s auth",
        http_cfg.host,
        http_cfg.port,
        http_cfg.path,
        http_cfg.auth_mode,
    )
    build_http_server(http_cfg).run(
        transport="streamable-http",
        host=http_cfg.host,
        port=http_cfg.port,
        path=http_cfg.path,
        uvicorn_config={"access_log": False},
    )


if __name__ == "__main__":  # pragma: no cover
    main()
