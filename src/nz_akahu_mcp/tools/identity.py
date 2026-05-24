"""Identity sub-server: 1 read tool + 1 write tool (always elicits).

Personal-App scope only. /categories, /parties, /connections, /identity/{id}
and POST /identity/{id}/verify-name are all app-scoped on Akahu
(see https://developers.akahu.nz/reference/api-akahu-io-authentication#app-scoped-endpoints)
and therefore unreachable -- not exposed as tools.

The user-scoped POST /verify/name endpoint IS exposed via `verify_name` below.
"""

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


# Not automatable: identity verification may incur a per-call charge from the
# bank and is identity-sensitive. Human-in-the-loop is the safer default.
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
    """Ask Akahu to verify a name against the account holder.

    family_name is required; given_name / middle_name / initials are optional.
    If account_id is provided, verification is scoped to that one account
    (POST /verify/name/{account_id}); otherwise Akahu matches against every
    identity source across all the user's connected accounts (POST /verify/name).

    Returns Akahu's match result. Note: this endpoint is documented user-scoped
    but requires the appropriate Personal-App scope grant in your Akahu portal.
    Without that grant Akahu returns 403 Forbidden.
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
