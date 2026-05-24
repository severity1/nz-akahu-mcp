"""Tests for the planning sub-server: 3 read tools."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from nz_akahu_mcp.models import Account, Transaction
from tests.conftest import load_fixture


def _txns() -> list[Transaction]:
    return [
        Transaction.model_validate(i)
        for i in load_fixture("insights_transactions")["items"]
    ]


def _async_iter(items: list[Transaction]) -> AsyncIterator[Transaction]:
    async def gen() -> AsyncIterator[Transaction]:
        for t in items:
            yield t

    return gen()


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    items = _txns()
    accounts = [
        Account.model_validate(i) for i in load_fixture("accounts")["items"]
    ]
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(items))
    client.get_account = AsyncMock(return_value=accounts[0])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


# ---------- project_balance ----------


async def test_project_balance(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.planning import project_balance

    result = await project_balance(account_id="acc_chq_001", days_ahead=30)
    assert result["account_id"] == "acc_chq_001"
    assert "current_balance_raw" in result
    assert "projected_balance_raw" in result
    assert result["days_ahead"] == 30


async def test_project_balance_no_balance(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.planning import project_balance

    acc = Account.model_validate(
        {**load_fixture("accounts")["items"][0], "balance": None}
    )
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([]))
    client.get_account = AsyncMock(return_value=acc)
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await project_balance(account_id="acc_chq_001")
    assert result["current_balance_raw"] is None
    assert result["projected_balance_raw"] is None


async def test_project_balance_no_transactions(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.planning import project_balance

    acc = Account.model_validate(load_fixture("accounts")["items"][0])
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([]))
    client.get_account = AsyncMock(return_value=acc)
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await project_balance(account_id="acc_chq_001")
    # With no recent activity, projection equals current.
    assert result["projected_balance_raw"] == result["current_balance_raw"]


# ---------- upcoming_recurring ----------


async def test_upcoming_recurring(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.planning import upcoming_recurring

    result = await upcoming_recurring(days_ahead=45)
    assert "upcoming" in result
    # Netflix should appear since gap ~30 days, last seen 2026-04-01.
    keys = {row["key"] for row in result["upcoming"]}
    assert "Netflix" in keys


async def test_upcoming_recurring_filters_out_far_future(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.planning import upcoming_recurring

    result = await upcoming_recurring(days_ahead=1)  # window way too small
    # nothing should fall in the next 24h based on our fixtures
    assert result["upcoming"] == []


async def test_upcoming_recurring_empty(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.planning import upcoming_recurring

    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([]))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await upcoming_recurring()
    assert result["upcoming"] == []


# ---------- savings_capacity ----------


async def test_savings_capacity(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.planning import savings_capacity

    result = await savings_capacity(lookback_days=200)
    assert "monthly_capacity_raw" in result
    assert "inflows_raw" in result
    assert "fixed_outflows_raw" in result


async def test_savings_capacity_empty(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.planning import savings_capacity

    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([]))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await savings_capacity()
    assert result["inflows_raw"] == 0


async def test_server_registers_three_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.planning import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"project_balance", "upcoming_recurring", "savings_capacity"}
