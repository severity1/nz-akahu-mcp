"""Tests for formatting helpers: money formatting, account masking, ISO dates."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_format_money_nzd_uses_dollar_symbol() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1234.56) == "$1,234.56"
    assert format_money(1234.56, "NZD") == "$1,234.56"


def test_format_money_nzd_negative() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(-89.99) == "-$89.99"


def test_format_money_zero() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(0) == "$0.00"
    assert format_money(0, "USD") == "USD 0.00"


def test_format_money_usd_uses_iso_prefix() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1234.56, "USD") == "USD 1,234.56"
    assert format_money(-89.99, "USD") == "-USD 89.99"


def test_format_money_eur_uses_iso_prefix() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1234.56, "EUR") == "EUR 1,234.56"


def test_format_money_php_uses_iso_prefix() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1234.56, "PHP") == "PHP 1,234.56"


def test_format_money_unknown_iso_code_passes_through() -> None:
    """Any non-NZD currency string is prefixed verbatim."""
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1000, "XOF") == "XOF 1,000.00"


def test_format_money_empty_currency_falls_back_to_nzd() -> None:
    """Empty currency defaults to NZD formatting."""
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1234.56, "") == "$1,234.56"


def test_format_money_large_number_thousands_separator() -> None:
    from nz_akahu_mcp.formatting import format_money

    assert format_money(1_234_567.89) == "$1,234,567.89"
    assert format_money(1_234_567.89, "USD") == "USD 1,234,567.89"


def test_format_money_rounds_half_to_even() -> None:
    """Banker's rounding (ROUND_HALF_EVEN) applies to all currencies."""
    from nz_akahu_mcp.formatting import format_money

    assert format_money(0.005) == "$0.00"
    assert format_money(0.015) == "$0.02"
    assert format_money(0.005, "USD") == "USD 0.00"
    assert format_money(0.015, "USD") == "USD 0.02"


def test_mask_account_full_format() -> None:
    from nz_akahu_mcp.formatting import mask_account

    assert mask_account("01-1234-1234567-00") == "01-****-***4567-00"


def test_mask_account_short_returns_input() -> None:
    """Already-masked or unrecognised strings should pass through unchanged."""
    from nz_akahu_mcp.formatting import mask_account

    assert mask_account("****") == "****"
    assert mask_account("") == ""


def test_mask_account_none_returns_empty() -> None:
    from nz_akahu_mcp.formatting import mask_account

    assert mask_account(None) == ""


def test_parse_iso_date_with_z() -> None:
    from nz_akahu_mcp.formatting import parse_iso_date

    dt = parse_iso_date("2026-05-20T00:00:00.000Z")
    assert dt == datetime(2026, 5, 20, 0, 0, 0, tzinfo=UTC)


def test_parse_iso_date_with_offset() -> None:
    from nz_akahu_mcp.formatting import parse_iso_date

    dt = parse_iso_date("2026-05-20T12:00:00+12:00")
    assert dt.utcoffset() is not None


def test_parse_iso_date_invalid_raises() -> None:
    from nz_akahu_mcp.formatting import parse_iso_date

    with pytest.raises(ValueError):
        parse_iso_date("not a date")
