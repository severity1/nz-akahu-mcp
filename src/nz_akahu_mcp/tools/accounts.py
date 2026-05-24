"""Accounts sub-server: 3 read tools + 2 write tools (both bypass-eligible)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.formatting import format_nzd, mask_account
from nz_akahu_mcp.models import Account
from nz_akahu_mcp.safety import require_write_consent

server: FastMCP[Any] = FastMCP("accounts")


def _summarise_account(account: Account) -> dict[str, Any]:
    """Convert an Account model to the LLM-facing dict shape (masked, formatted)."""
    return {
        "id": account.id,
        "name": account.name,
        "type": account.type,
        "status": account.status,
        "formatted_account": mask_account(account.formatted_account),
        "connection": account.connection.name if account.connection else None,
        "balance": format_nzd(account.balance.current) if account.balance else None,
        "currency": account.balance.currency if account.balance else None,
    }


@server.tool
async def list_accounts() -> dict[str, Any]:
    """List every connected account with masked numbers and formatted balances."""
    accounts = await deps.get_client().list_accounts()
    return {"accounts": [_summarise_account(a) for a in accounts]}


@server.tool
async def get_account(account_id: str) -> dict[str, Any]:
    """Fetch a single account by id. Returns masked account number and balance."""
    account = await deps.get_client().get_account(account_id)
    return _summarise_account(account)


@server.tool
async def get_account_balance(account_id: str) -> dict[str, Any]:
    """Return just the balance for an account (lighter than full account details)."""
    account = await deps.get_client().get_account(account_id)
    if account.balance is None:
        return {"id": account.id, "balance": None, "available": None, "currency": None}
    return {
        "id": account.id,
        "balance": format_nzd(account.balance.current),
        "available": format_nzd(account.balance.available)
        if account.balance.available is not None
        else None,
        "currency": account.balance.currency,
    }


# Automatable criteria satisfied:
#   1. Idempotent: repeated refresh calls just no-op past rate limits.
#   2. No third-party side effects: pings Akahu, no humans notified, no money moved.
#   3. Self-corrects next cycle: a redundant refresh costs only a rate-limit token.
#   4. Common automation use case: nightly refresh script before morning analysis.
@server.tool
@require_write_consent(
    "Refresh data for all your connected accounts. This is rate-limited by your bank.",
    automatable=True,
)
async def refresh_all_accounts(*, ctx: Context) -> dict[str, Any]:
    """Trigger Akahu to fetch fresh data for every connected account."""
    result = await deps.get_client().refresh_all()
    return {"success": result.success, "message": result.message}


# Automatable criteria satisfied:
#   1. Idempotent: redundant refreshes are no-ops.
#   2. No third-party side effects: just a fetch trigger.
#   3. Self-corrects next cycle.
#   4. Common automation use case: refresh only the chequing account before payday checks.
@server.tool
@require_write_consent(
    "Refresh data for account {account_id}. Rate-limited by your bank.",
    automatable=True,
)
async def refresh_account(*, ctx: Context, account_id: str) -> dict[str, Any]:
    """Trigger Akahu to fetch fresh data for one specific account."""
    result = await deps.get_client().refresh_one(account_id)
    return {"success": result.success, "message": result.message, "account_id": account_id}
