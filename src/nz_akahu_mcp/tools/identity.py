"""Identity sub-server: 1 read tool + 1 write tool.

Exposes only the user-scoped Akahu identity endpoints. App-scoped endpoints
(`/categories`, `/parties`, `/connections`, `/identity/{id}/verify-name`) are
not reachable from a Personal App and are not shipped.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.safety import require_write_consent

server: FastMCP[Any] = FastMCP("identity")


@server.tool
async def get_me() -> dict[str, Any]:
    """Return identity/profile data for the connected Akahu user.

    Returns:
        {"id": str, "email": str | None, "name": str | None}
        where name concatenates profile first_name and last_name when present.
    """
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
@require_write_consent(
    "Verify the name '{given_name} {family_name}' "
    "(account scope: {account_id}). This sends an identity check to your bank "
    "and may incur a per-call charge.",
    automatable=False,
)
async def verify_name(
    *,
    ctx: Context,
    family_name: str,
    given_name: str | None = None,
    middle_name: str | None = None,
    initials: list[str] | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Verify a name against the account holder via Akahu's identity check.

    If account_id is provided, the check is scoped to that one account
    (POST /verify/name/{account_id}); otherwise Akahu matches against every
    identity source the user has connected (POST /verify/name).

    Requires the appropriate Personal-App scope grant in your Akahu portal;
    without it Akahu returns 403 Forbidden. May incur a per-call charge from
    your bank. Always elicits user confirmation (not bypass-eligible).

    Returns {"success": bool, "item": dict | None, "message": str | None}
    where item is Akahu's match-result envelope (shape documented at
    https://developers.akahu.nz/docs/enduring-verify-name).

    Args:
        family_name: Required. Surname to verify.
        given_name: Optional first name.
        middle_name: Optional middle name.
        initials: Optional list of initial strings (e.g. ["J", "R"]).
        account_id: Optional account scope; omit to check all sources.
    """
    result = await deps.get_client().verify_name(
        family_name=family_name,
        given_name=given_name,
        middle_name=middle_name,
        initials=initials,
        account_id=account_id,
    )
    return {
        "success": result.success,
        "item": result.item,
        "message": result.message,
    }
