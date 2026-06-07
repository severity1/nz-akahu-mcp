"""Root FastMCP server. Mounts sub-servers and runs over stdio."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from nz_akahu_mcp.config import AkahuConfig
from nz_akahu_mcp.safety import bypass_eligible_tools
from nz_akahu_mcp.tools import accounts, identity, transactions

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = (
    "Use Akahu tools only for the connected user's New Zealand banking data. "
    "For last-month transactions, call txn_get_transactions with explicit "
    "start_date and end_date values. Prefer read tools. Write tools refresh "
    "data or send support/identity requests and are guarded by read-only mode "
    "and consent."
)


def build_server() -> FastMCP[Any]:
    """Construct the root FastMCP server with all sub-servers mounted."""
    mcp: FastMCP[Any] = FastMCP(
        "nz-akahu-mcp",
        instructions=SERVER_INSTRUCTIONS,
    )
    mcp.mount(accounts.server, namespace="acct")
    mcp.mount(transactions.server, namespace="txn")
    mcp.mount(identity.server, namespace="id")
    return mcp


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


def main() -> None:
    """Entry point used by the `nz-akahu-mcp` console script."""
    logging.basicConfig(
        level=AkahuConfig().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log_startup_banner()
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
