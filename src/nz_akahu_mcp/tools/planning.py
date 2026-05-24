"""Planning sub-server: 3 forecast tools, all read-only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp import FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.formatting import format_nzd
from nz_akahu_mcp.tools.insights import (
    _aware,
    _build_groups,
    _classify_group,
    _collect,
    _in_window,
    cash_flow_summary,
)

server: FastMCP[Any] = FastMCP("planning")


@server.tool
async def project_balance(account_id: str, days_ahead: int = 30) -> dict[str, Any]:
    """Linearly extrapolate the balance N days into the future.

    Uses mean daily net change over the past 30 days. If there's no balance or
    no recent activity, the projection equals the current balance.
    """
    account = await deps.get_client().get_account(account_id)
    if account.balance is None:
        return {
            "account_id": account_id,
            "days_ahead": days_ahead,
            "current_balance_raw": None,
            "projected_balance_raw": None,
        }

    end = datetime.now(tz=UTC)
    start = end - timedelta(days=30)
    txns = await _collect(start=start.isoformat(), end=end.isoformat())
    recent = [
        t for t in txns if t.account == account_id and _in_window(t, start, end)
    ]
    net_change = sum(t.amount for t in recent)
    daily_net = net_change / 30.0 if recent else 0.0
    projected = account.balance.current + daily_net * days_ahead

    return {
        "account_id": account_id,
        "days_ahead": days_ahead,
        "current_balance": format_nzd(account.balance.current),
        "current_balance_raw": account.balance.current,
        "projected_balance": format_nzd(projected),
        "projected_balance_raw": projected,
        "daily_net_raw": daily_net,
    }


@server.tool
async def upcoming_recurring(days_ahead: int = 30) -> dict[str, Any]:
    """Forecast next occurrences of recurring payments within the window.

    Surfaces both HIGH and MEDIUM confidence groups, tagged.
    """
    now = datetime.now(tz=UTC)
    horizon = now + timedelta(days=days_ahead)
    lookback_start = now - timedelta(days=200)
    txns = await _collect(start=lookback_start.isoformat(), end=now.isoformat())
    txns = [t for t in txns if _in_window(t, lookback_start, now)]
    groups = _build_groups(txns)

    upcoming: list[dict[str, Any]] = []
    for group in groups.values():
        _confidence, summary = _classify_group(group)
        if summary is None:
            continue
        last_seen = max(_aware(t.date) for t in group.txns)
        gap = timedelta(days=summary["mean_gap_days"])
        if gap.total_seconds() <= 0:  # pragma: no cover  # why: _classify_group enforces min gap
            continue
        # Step forward from last_seen until we're past 'now', then collect
        # every projected occurrence inside [now, horizon].
        next_due = last_seen + gap
        while next_due < now:
            next_due += gap
        while next_due <= horizon:
            upcoming.append({**summary, "next_due": next_due.date().isoformat()})
            next_due += gap
    upcoming.sort(key=lambda r: r["next_due"])
    return {"upcoming": upcoming}


@server.tool
async def savings_capacity(lookback_days: int = 90) -> dict[str, Any]:
    """Estimate monthly savings capacity: inflows minus HIGH-confidence fixed outflows."""
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)
    summary = await cash_flow_summary(start.isoformat(), end.isoformat())

    months = max(lookback_days / 30.0, 1.0)
    inflows_monthly = summary["inflows_raw"] / months
    fixed_monthly = summary["fixed_outflows_raw"] / months
    capacity = inflows_monthly - fixed_monthly
    return {
        "monthly_capacity": format_nzd(capacity),
        "monthly_capacity_raw": capacity,
        "inflows": summary["inflows"],
        "inflows_raw": summary["inflows_raw"],
        "fixed_outflows": summary["fixed_outflows"],
        "fixed_outflows_raw": summary["fixed_outflows_raw"],
        "months_analysed": round(months, 1),
    }
