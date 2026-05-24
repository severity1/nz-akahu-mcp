"""Small display helpers: currency formatting, account masking, ISO date parsing."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

# NZ bank-account format: BB-bbbb-AAAAAAA-SS
# (bank code - branch - account number - suffix)
_NZ_ACCOUNT_RE = re.compile(r"^(\d{2})-(\d{4})-(\d{7})-(\d{2,3})$")


def format_money(amount: float | int | Decimal, currency: str = "NZD") -> str:
    """Format a numeric amount as a currency string.

    NZD uses the dollar sign; any other ISO 4217 code is used as a verbatim
    prefix. Empty/missing currency falls back to NZD.

    >>> format_money(1234.56)
    '$1,234.56'
    >>> format_money(-89.99)
    '-$89.99'
    >>> format_money(1234.56, "USD")
    'USD 1,234.56'
    >>> format_money(-89.99, "EUR")
    '-EUR 89.99'
    """
    quantised = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    sign = "-" if quantised < 0 else ""
    absolute = abs(quantised)
    integer_part, _, fractional = format(absolute, "f").partition(".")
    with_commas = f"{int(integer_part):,}"
    if currency == "NZD" or not currency:
        return f"{sign}${with_commas}.{fractional}"
    return f"{sign}{currency} {with_commas}.{fractional}"


def mask_account(formatted: str | None) -> str:
    """Mask the middle of a NZ account number, preserving bank + last 4 of account.

    Input:  '01-1234-1234567-00'
    Output: '01-****-***4567-00'
    Any non-matching input passes through unchanged (empty for None).
    """
    if not formatted:
        return ""
    match = _NZ_ACCOUNT_RE.match(formatted)
    if not match:
        return formatted
    bank, _branch, account, suffix = match.groups()
    last4 = account[-4:]
    return f"{bank}-****-***{last4}-{suffix}"


def parse_iso_date(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, accepting trailing 'Z' (UTC).

    Akahu returns timestamps like '2026-05-20T00:00:00.000Z'.
    """
    normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalised)
