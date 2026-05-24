"""Insights sub-server: 6 analytical tools, all read-only.

Recurring detector is two-tier (HIGH/MEDIUM confidence). cash_flow_summary
only treats HIGH-confidence groups as 'fixed outflows' so erratic bills don't
distort the savings-capacity calculation. find_recurring_payments returns both
tiers tagged so consumers can decide.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastmcp import FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.formatting import format_nzd, parse_iso_date
from nz_akahu_mcp.models import Transaction

server: FastMCP[Any] = FastMCP("insights")

GroupBy = Literal["category", "merchant", "account"]

# Two-tier recurring-payment thresholds (decided by the user during build).
_HIGH_AMOUNT_TOLERANCE = 0.05  # +/-5%
_HIGH_GAP_STDEV_DAYS = 7.0
_MEDIUM_AMOUNT_TOLERANCE = 0.30  # +/-30%
_MEDIUM_GAP_STDEV_DAYS = 10.0
_MIN_OCCURRENCES = 3
_MIN_GAP_DAYS = 5
_MAX_GAP_DAYS = 400


# ---------- helpers ----------


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _collect(
    *, start: str | None = None, end: str | None = None
) -> list[Transaction]:
    return [t async for t in deps.get_client().iter_transactions(start=start, end=end)]


def _in_window(txn: Transaction, start: datetime, end: datetime) -> bool:
    d = _aware(txn.date)
    return start <= d < end


# ---------- analyse_spending ----------


@server.tool
async def analyse_spending(
    start_date: str, end_date: str, group_by: GroupBy = "category"
) -> dict[str, Any]:
    """Group outflows in a date window by category, merchant, or account.

    Inflows (positive amounts) are excluded.
    """
    start = _aware(parse_iso_date(start_date))
    end = _aware(parse_iso_date(end_date))
    txns = await _collect(start=start_date, end=end_date)

    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for txn in txns:
        if txn.amount >= 0:
            continue
        if not _in_window(txn, start, end):
            continue
        if group_by == "category":
            key = txn.category.name if txn.category else "Uncategorised"
        elif group_by == "merchant":
            key = txn.merchant.name if txn.merchant else "Unknown"
        else:  # group_by == "account"
            key = txn.account
        totals[key] += -txn.amount  # present as positive spend
        counts[key] += 1

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    groups = [
        {
            "key": key,
            "total": format_nzd(total),
            "total_raw": total,
            "count": counts[key],
        }
        for key, total in ranked
    ]
    return {"group_by": group_by, "groups": groups}


# ---------- recurring detector ----------


@dataclass
class _Group:
    key: str
    txns: list[Transaction] = field(default_factory=list)


def _group_key(txn: Transaction) -> str:
    """Group debits by merchant id when present, else normalised description."""
    if txn.merchant:
        return f"m:{txn.merchant.id}"
    normalised = "".join(c if c.isalnum() else " " for c in txn.description.lower())
    return "d:" + " ".join(normalised.split())


def _classify_group(group: _Group) -> tuple[str | None, dict[str, Any] | None]:
    """Return (confidence, summary) or (None, None) if not recurring."""
    sorted_txns = sorted(group.txns, key=lambda t: _aware(t.date))
    if len(sorted_txns) < _MIN_OCCURRENCES:
        return None, None

    amounts = [abs(t.amount) for t in sorted_txns]
    median_amount = statistics.median(amounts)
    if median_amount == 0:
        return None, None  # pragma: no cover  # why: defensive, real txns are non-zero
    max_dev_ratio = max(abs(a - median_amount) / median_amount for a in amounts)

    gaps = [
        (_aware(b.date) - _aware(a.date)).days
        for a, b in zip(sorted_txns, sorted_txns[1:], strict=False)
    ]
    mean_gap = statistics.mean(gaps)
    if not (_MIN_GAP_DAYS <= mean_gap <= _MAX_GAP_DAYS):
        return None, None
    gap_stdev = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0

    display_key = (
        sorted_txns[0].merchant.name
        if sorted_txns[0].merchant
        else sorted_txns[0].description
    )
    summary: dict[str, Any] = {
        "key": display_key,
        "occurrences": len(sorted_txns),
        "median_amount": format_nzd(median_amount),
        "median_amount_raw": median_amount,
        "mean_gap_days": round(mean_gap, 1),
        "last_seen": sorted_txns[-1].date.date().isoformat(),
    }

    if max_dev_ratio <= _HIGH_AMOUNT_TOLERANCE and gap_stdev < _HIGH_GAP_STDEV_DAYS:
        summary["confidence"] = "HIGH"
        return "HIGH", summary
    if max_dev_ratio <= _MEDIUM_AMOUNT_TOLERANCE and gap_stdev < _MEDIUM_GAP_STDEV_DAYS:
        summary["confidence"] = "MEDIUM"
        return "MEDIUM", summary
    return None, None


def _build_groups(txns: Iterable[Transaction]) -> dict[str, _Group]:
    groups: dict[str, _Group] = {}
    for txn in txns:
        if txn.amount >= 0:
            continue
        key = _group_key(txn)
        groups.setdefault(key, _Group(key=key)).txns.append(txn)
    return groups


@server.tool
async def find_recurring_payments(lookback_days: int = 90) -> dict[str, Any]:
    """Detect recurring debits. Returns HIGH and MEDIUM confidence groups, tagged."""
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)
    txns = await _collect(start=start.isoformat(), end=end.isoformat())
    txns = [t for t in txns if _in_window(t, start, end)]
    groups = _build_groups(txns)

    recurring: list[dict[str, Any]] = []
    for group in groups.values():
        _confidence, summary = _classify_group(group)
        if summary is not None:
            recurring.append(summary)
    recurring.sort(key=lambda r: r["median_amount_raw"], reverse=True)
    return {"recurring": recurring}


# ---------- cash_flow_summary ----------


@server.tool
async def cash_flow_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """Sum inflows, outflows, net, and the HIGH-confidence fixed-outflow portion."""
    start = _aware(parse_iso_date(start_date))
    end = _aware(parse_iso_date(end_date))
    txns = await _collect(start=start_date, end=end_date)

    inflows = 0.0
    outflows = 0.0
    in_window: list[Transaction] = []
    for txn in txns:
        if not _in_window(txn, start, end):
            continue
        in_window.append(txn)
        if txn.amount >= 0:
            inflows += txn.amount
        else:
            outflows += -txn.amount

    fixed = 0.0
    for group in _build_groups(in_window).values():
        confidence, summary = _classify_group(group)
        if confidence == "HIGH" and summary is not None:
            fixed += summary["median_amount_raw"] * summary["occurrences"]

    net = inflows - outflows
    return {
        "inflows": format_nzd(inflows),
        "inflows_raw": inflows,
        "outflows": format_nzd(outflows),
        "outflows_raw": outflows,
        "net": format_nzd(net),
        "net_raw": net,
        "fixed_outflows": format_nzd(fixed),
        "fixed_outflows_raw": fixed,
    }


# ---------- compare_periods ----------


@server.tool
async def compare_periods(
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
) -> dict[str, Any]:
    """Run cash_flow_summary for two periods and report the delta."""
    a = await cash_flow_summary(period_a_start, period_a_end)
    b = await cash_flow_summary(period_b_start, period_b_end)
    return {
        "period_a": a,
        "period_b": b,
        "delta_inflows_raw": b["inflows_raw"] - a["inflows_raw"],
        "delta_outflows_raw": b["outflows_raw"] - a["outflows_raw"],
        "delta_net_raw": b["net_raw"] - a["net_raw"],
    }


# ---------- top_merchants ----------


@server.tool
async def top_merchants(
    start_date: str, end_date: str, limit: int = 10
) -> dict[str, Any]:
    """Top N merchants by total spend in a window."""
    start = _aware(parse_iso_date(start_date))
    end = _aware(parse_iso_date(end_date))
    txns = await _collect(start=start_date, end=end_date)

    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for txn in txns:
        if txn.amount >= 0 or not _in_window(txn, start, end) or txn.merchant is None:
            continue
        totals[txn.merchant.name] += -txn.amount
        counts[txn.merchant.name] += 1

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return {
        "merchants": [
            {
                "name": name,
                "total": format_nzd(total),
                "total_raw": total,
                "count": counts[name],
            }
            for name, total in ranked
        ]
    }


# ---------- detect_unusual_transactions ----------


def _mad(values: list[float]) -> float:
    """Median absolute deviation."""
    median_value = statistics.median(values)
    return statistics.median([abs(v - median_value) for v in values])


@server.tool
async def detect_unusual_transactions(
    lookback_days: int = 30, threshold_multiplier: float = 3.0
) -> dict[str, Any]:
    """Flag debits whose amount is more than threshold * MAD from category median."""
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)
    txns = await _collect(start=start.isoformat(), end=end.isoformat())
    by_category: dict[str, list[Transaction]] = defaultdict(list)
    for txn in txns:
        if txn.amount >= 0 or not _in_window(txn, start, end):
            continue
        key = txn.category.name if txn.category else "Uncategorised"
        by_category[key].append(txn)

    unusual: list[dict[str, Any]] = []
    for category, items in by_category.items():
        if len(items) < 3:
            continue
        amounts = [abs(t.amount) for t in items]
        median_amount = statistics.median(amounts)
        deviation = _mad(amounts)
        if deviation == 0:
            continue  # all identical -> nothing is unusual
        for txn in items:
            score = abs(abs(txn.amount) - median_amount) / deviation
            if score > threshold_multiplier:
                unusual.append(
                    {
                        "id": txn.id,
                        "date": txn.date.date().isoformat(),
                        "description": txn.description,
                        "amount": format_nzd(txn.amount),
                        "amount_raw": txn.amount,
                        "category": category,
                        "score": round(score, 2),
                    }
                )
    unusual.sort(key=lambda row: row["score"], reverse=True)
    return {"unusual": unusual}
