"""Tests for the insights sub-server: 6 analytical tools, all read-only."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest

from nz_akahu_mcp.models import Transaction
from tests.conftest import load_fixture


def _txns() -> list[Transaction]:
    return [Transaction.model_validate(i) for i in load_fixture("insights_transactions")["items"]]


def _async_iter(items: list[Transaction]) -> AsyncIterator[Transaction]:
    async def gen() -> AsyncIterator[Transaction]:
        for t in items:
            yield t

    return gen()


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    items = _txns()
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(items))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


@pytest.fixture
def empty_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([]))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


# ---------- analyse_spending ----------


async def test_analyse_spending_by_category(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import analyse_spending

    result = await analyse_spending(
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        group_by="category",
    )
    by_cat = {row["key"]: row for row in result["groups"]}
    assert "Entertainment" in by_cat
    assert by_cat["Entertainment"]["count"] == 4
    # Sums should be positive (we present total *spent*, not the negative)
    assert by_cat["Entertainment"]["total_raw"] == pytest.approx(99.96)


async def test_analyse_spending_by_merchant(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import analyse_spending

    result = await analyse_spending(
        start_date="2026-04-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        group_by="merchant",
    )
    keys = {row["key"] for row in result["groups"]}
    assert "Countdown" in keys


async def test_analyse_spending_by_account(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import analyse_spending

    result = await analyse_spending(
        start_date="2026-04-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        group_by="account",
    )
    assert any(row["key"] == "acc_chq_001" for row in result["groups"])


async def test_analyse_spending_ignores_income(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import analyse_spending

    result = await analyse_spending(
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        group_by="category",
    )
    keys = {row["key"] for row in result["groups"]}
    assert "Salary" not in keys


async def test_analyse_spending_empty(fake_env: None, empty_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import analyse_spending

    result = await analyse_spending(
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        group_by="category",
    )
    assert result["groups"] == []


async def test_analyse_spending_handles_missing_merchant_category(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.insights import analyse_spending

    plain = Transaction.model_validate(
        {
            "_id": "txn_x",
            "_account": "acc",
            "date": "2026-04-10T00:00:00Z",
            "description": "FOO",
            "amount": -10.00,
            "type": "EFTPOS",
        }
    )
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([plain]))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    for group_by in ("category", "merchant"):
        result = await analyse_spending(
            start_date="2026-04-01T00:00:00Z",
            end_date="2026-05-01T00:00:00Z",
            group_by=group_by,
        )
        # uncategorised/no-merchant bucket should still appear
        keys = {row["key"] for row in result["groups"]}
        assert "Uncategorised" in keys or "Unknown" in keys


# ---------- find_recurring_payments ----------


async def test_find_recurring_high_confidence_netflix(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.insights import find_recurring_payments

    result = await find_recurring_payments(lookback_days=200)
    high = [g for g in result["recurring"] if g["confidence"] == "HIGH"]
    keys = {g["key"] for g in high}
    assert "Netflix" in keys


async def test_find_recurring_medium_confidence_genesis(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.insights import find_recurring_payments

    result = await find_recurring_payments(lookback_days=200)
    medium = [g for g in result["recurring"] if g["confidence"] == "MEDIUM"]
    keys = {g["key"] for g in medium}
    # Power varies ~25% which is outside HIGH but inside MEDIUM band
    assert "Genesis Energy" in keys


async def test_find_recurring_ignores_inflows(
    fake_env: None, patched_client: MagicMock
) -> None:
    """Salary is positive amount; only outflows count as recurring payments."""
    from nz_akahu_mcp.tools.insights import find_recurring_payments

    result = await find_recurring_payments(lookback_days=200)
    keys = {g["key"] for g in result["recurring"]}
    assert "Salary" not in keys


async def test_find_recurring_ignores_too_few_occurrences(
    fake_env: None, patched_client: MagicMock
) -> None:
    """Coffee shop only has 2 records, below the >=3 threshold."""
    from nz_akahu_mcp.tools.insights import find_recurring_payments

    result = await find_recurring_payments(lookback_days=200)
    keys = {g["key"] for g in result["recurring"]}
    assert "Allpress" not in keys


async def test_find_recurring_empty(fake_env: None, empty_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import find_recurring_payments

    result = await find_recurring_payments()
    assert result["recurring"] == []


# ---------- cash_flow_summary ----------


async def test_cash_flow_summary_totals(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import cash_flow_summary

    result = await cash_flow_summary(
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
    )
    assert result["inflows_raw"] == pytest.approx(18000.0)
    assert result["outflows_raw"] > 0
    assert result["net_raw"] == pytest.approx(result["inflows_raw"] - result["outflows_raw"])
    assert isinstance(result["fixed_outflows_raw"], float)


async def test_cash_flow_summary_empty(fake_env: None, empty_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import cash_flow_summary

    result = await cash_flow_summary(
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
    )
    assert result["inflows_raw"] == 0
    assert result["outflows_raw"] == 0


# ---------- compare_periods ----------


async def test_compare_periods(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import compare_periods

    result = await compare_periods(
        period_a_start="2026-01-01T00:00:00Z",
        period_a_end="2026-03-01T00:00:00Z",
        period_b_start="2026-03-01T00:00:00Z",
        period_b_end="2026-05-01T00:00:00Z",
    )
    assert "period_a" in result
    assert "period_b" in result
    assert "delta_net_raw" in result


# ---------- top_merchants ----------


async def test_top_merchants(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import top_merchants

    result = await top_merchants(
        start_date="2026-04-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
        limit=3,
    )
    assert len(result["merchants"]) <= 3
    assert all("name" in row for row in result["merchants"])
    # Countdown has the biggest spend in April (4 txns including the 650 outlier)
    assert result["merchants"][0]["name"] == "Countdown"


async def test_top_merchants_empty(fake_env: None, empty_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.insights import top_merchants

    result = await top_merchants(
        start_date="2026-04-01T00:00:00Z",
        end_date="2026-05-01T00:00:00Z",
    )
    assert result["merchants"] == []


# ---------- detect_unusual_transactions ----------


async def test_detect_unusual_flags_huge_grocery(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.insights import detect_unusual_transactions

    result = await detect_unusual_transactions(lookback_days=120, threshold_multiplier=3.0)
    flagged_ids = {row["id"] for row in result["unusual"]}
    assert "i16" in flagged_ids  # the 650 outlier


async def test_detect_unusual_handles_no_outliers(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All transactions within MAD threshold -> empty list."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.insights import detect_unusual_transactions

    items = [
        Transaction.model_validate(
            {
                "_id": f"t{i}",
                "_account": "acc",
                "date": "2026-04-10T00:00:00Z",
                "description": "STEADY",
                "amount": -50.00,
                "type": "EFTPOS",
                "category": {"_id": "c", "name": "Cat"},
            }
        )
        for i in range(10)
    ]
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(items))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await detect_unusual_transactions()
    assert result["unusual"] == []


async def test_detect_unusual_skips_categories_with_too_few(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Need >= 3 transactions in a category to compute median/MAD."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.insights import detect_unusual_transactions

    items = [
        Transaction.model_validate(
            {
                "_id": "tt1",
                "_account": "acc",
                "date": "2026-04-10T00:00:00Z",
                "description": "ONE",
                "amount": -5.00,
                "type": "EFTPOS",
                "category": {"_id": "c", "name": "Cat"},
            }
        ),
        Transaction.model_validate(
            {
                "_id": "tt2",
                "_account": "acc",
                "date": "2026-04-11T00:00:00Z",
                "description": "TWO",
                "amount": -500.00,
                "type": "EFTPOS",
                "category": {"_id": "c", "name": "Cat"},
            }
        ),
    ]
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(items))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await detect_unusual_transactions()
    assert result["unusual"] == []


async def test_detect_unusual_handles_zero_mad(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If MAD=0 (all same amount), the detector must not divide by zero."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.insights import detect_unusual_transactions

    items = [
        Transaction.model_validate(
            {
                "_id": f"t{i}",
                "_account": "acc",
                "date": "2026-04-10T00:00:00Z",
                "description": "SAME",
                "amount": -10.00,
                "type": "EFTPOS",
                "category": {"_id": "c", "name": "Cat"},
            }
        )
        for i in range(5)
    ]
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(items))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await detect_unusual_transactions()
    assert result["unusual"] == []


async def test_server_registers_six_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.insights import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "analyse_spending",
        "find_recurring_payments",
        "cash_flow_summary",
        "compare_periods",
        "top_merchants",
        "detect_unusual_transactions",
    }
