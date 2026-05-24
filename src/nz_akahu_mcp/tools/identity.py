"""Identity sub-server: 3 read tools + 1 write tool (always elicits)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.safety import require_write_consent

server: FastMCP[Any] = FastMCP("identity")


@server.tool
async def get_me() -> dict[str, Any]:
    """Return identity/profile data for the connected Akahu user."""
    me = await deps.get_client().get_me()
    name: str | None = None
    if me.profile and (me.profile.first_name or me.profile.last_name):
        name = " ".join(p for p in (me.profile.first_name, me.profile.last_name) if p)
    return {
        "id": me.id,
        "email": me.email,
        "name": name,
    }


@server.tool
async def list_parties() -> dict[str, Any]:
    """List counterparties known to Akahu for the user's accounts."""
    parties = await deps.get_client().list_parties()
    return {
        "parties": [
            {
                "id": p.id,
                "account_id": p.account,
                "type": p.type,
                "name": p.name,
                "address": p.address,
            }
            for p in parties
        ]
    }


@server.tool
async def list_categories() -> dict[str, Any]:
    """List the NZFCC category reference used by Akahu transaction enrichment."""
    cats = await deps.get_client().list_categories()
    return {
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "groups": {gk: gv.name for gk, gv in c.groups.items()},
            }
            for c in cats
        ]
    }


# Not automatable: identity verification may incur a per-call charge from the
# bank and is identity-sensitive. Human-in-the-loop is the safer default.
@server.tool
@require_write_consent(
    "Verify the name '{name}' against account {account_id}. This sends an "
    "identity check to your bank and may incur a per-call charge.",
    automatable=False,
)
async def verify_name(*, ctx: Context, account_id: str, name: str) -> dict[str, Any]:
    """Ask Akahu to confirm whether the given name matches the account holder."""
    result = await deps.get_client().verify_name(account_id, name)
    return {
        "success": result.success,
        "item": result.item,
        "message": result.message,
    }
