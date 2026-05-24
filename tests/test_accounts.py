"""Tests for the accounts sub-server."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from nz_akahu_mcp.models import Account, RefreshResult
from tests.conftest import load_fixture


def _fake_client() -> MagicMock:
    """Build a MagicMock with AsyncMock methods matching AkahuClient."""
    client = MagicMock()
    items = load_fixture("accounts")["items"]
    client.list_accounts = AsyncMock(return_value=[Account.model_validate(i) for i in items])
    client.get_account = AsyncMock(return_value=Account.model_validate(items[0]))
    client.refresh_all = AsyncMock(return_value=RefreshResult(success=True))
    client.refresh_one = AsyncMock(return_value=RefreshResult(success=True))
    return client


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    client = _fake_client()
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


# ---------- list_accounts ----------


async def test_list_accounts_returns_masked(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.accounts import list_accounts

    result = await list_accounts()
    assert len(result["accounts"]) == 2
    a0 = result["accounts"][0]
    assert a0["id"] == "acc_chq_001"
    assert a0["name"] == "Everyday account"
    assert a0["formatted_account"] == "01-****-***4567-00"
    assert a0["balance"] == "$2,543.21"
    assert a0["currency"] == "NZD"


async def test_list_accounts_empty(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.accounts import list_accounts

    client = MagicMock()
    client.list_accounts = AsyncMock(return_value=[])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await list_accounts()
    assert result["accounts"] == []


async def test_list_accounts_handles_missing_balance(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.accounts import list_accounts

    item = load_fixture("accounts")["items"][0]
    item = {**item, "balance": None}
    client = MagicMock()
    client.list_accounts = AsyncMock(return_value=[Account.model_validate(item)])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await list_accounts()
    assert result["accounts"][0]["balance"] is None
    assert result["accounts"][0]["currency"] is None


async def test_list_accounts_renders_non_nzd_with_iso_prefix(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A USD-denominated account (e.g. Wise) should render 'USD 2,543.21'."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.accounts import list_accounts

    item = load_fixture("accounts")["items"][0]
    item = {**item, "balance": {**item["balance"], "currency": "USD"}}
    client = MagicMock()
    client.list_accounts = AsyncMock(return_value=[Account.model_validate(item)])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await list_accounts()
    assert result["accounts"][0]["balance"] == "USD 2,543.21"
    assert result["accounts"][0]["currency"] == "USD"


# ---------- get_account ----------


async def test_get_account_returns_masked(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.accounts import get_account

    result = await get_account(account_id="acc_chq_001")
    assert result["id"] == "acc_chq_001"
    assert result["formatted_account"] == "01-****-***4567-00"
    assert result["balance"] == "$2,543.21"
    patched_client.get_account.assert_awaited_once_with("acc_chq_001")


# ---------- get_account_balance ----------


async def test_get_account_balance(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.accounts import get_account_balance

    result = await get_account_balance(account_id="acc_chq_001")
    assert result["balance"] == "$2,543.21"
    assert result["available"] == "$2,543.21"
    assert result["currency"] == "NZD"


async def test_get_account_balance_no_balance(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.accounts import get_account_balance

    item = {**load_fixture("accounts")["items"][0], "balance": None}
    client = MagicMock()
    client.get_account = AsyncMock(return_value=Account.model_validate(item))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_account_balance(account_id="acc_chq_001")
    assert result["balance"] is None


# ---------- refresh_all_accounts (write, automatable) ----------


async def test_refresh_all_blocks_in_readonly(
    fake_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ReadOnlyError
    from nz_akahu_mcp.tools.accounts import refresh_all_accounts

    ctx = ctx_factory(elicit_action="accept")
    with pytest.raises(ReadOnlyError):
        await refresh_all_accounts(ctx=ctx)
    patched_client.refresh_all.assert_not_awaited()


async def test_refresh_all_proceeds_on_accept(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.accounts import refresh_all_accounts

    ctx = ctx_factory(elicit_action="accept")
    result = await refresh_all_accounts(ctx=ctx)
    assert result["success"] is True
    patched_client.refresh_all.assert_awaited_once()


async def test_refresh_all_aborts_on_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.accounts import refresh_all_accounts

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await refresh_all_accounts(ctx=ctx)
    patched_client.refresh_all.assert_not_awaited()


async def test_refresh_all_aborts_on_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.accounts import refresh_all_accounts

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationDeclinedError):
        await refresh_all_accounts(ctx=ctx)
    patched_client.refresh_all.assert_not_awaited()


async def test_refresh_all_bypassed_when_automation_on(
    bypass_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.accounts import refresh_all_accounts

    ctx = ctx_factory(elicit_action="decline")  # would normally abort
    result = await refresh_all_accounts(ctx=ctx)
    assert result["success"] is True
    ctx.elicit.assert_not_awaited()
    patched_client.refresh_all.assert_awaited_once()


# ---------- refresh_account (write, automatable) ----------


async def test_refresh_account_blocks_in_readonly(
    fake_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ReadOnlyError
    from nz_akahu_mcp.tools.accounts import refresh_account

    ctx = ctx_factory()
    with pytest.raises(ReadOnlyError):
        await refresh_account(ctx=ctx, account_id="acc_chq_001")


async def test_refresh_account_proceeds_on_accept(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.accounts import refresh_account

    ctx = ctx_factory(elicit_action="accept")
    result = await refresh_account(ctx=ctx, account_id="acc_chq_001")
    assert result["success"] is True
    patched_client.refresh_one.assert_awaited_once_with("acc_chq_001")
    # confirm account_id rendered into the elicit prompt
    msg = ctx.elicit.await_args[0][0]
    assert "acc_chq_001" in msg


async def test_refresh_account_aborts_on_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.accounts import refresh_account

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await refresh_account(ctx=ctx, account_id="acc_chq_001")


async def test_refresh_account_aborts_on_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.accounts import refresh_account

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationDeclinedError):
        await refresh_account(ctx=ctx, account_id="acc_chq_001")


async def test_refresh_account_bypassed_when_automation_on(
    bypass_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.accounts import refresh_account

    ctx = ctx_factory(elicit_action="decline")
    result = await refresh_account(ctx=ctx, account_id="acc_chq_001")
    assert result["success"] is True
    ctx.elicit.assert_not_awaited()


# ---------- get_pending_transactions (per-account) ----------


async def test_account_pending_transactions(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.models import Transaction
    from nz_akahu_mcp.tools.accounts import get_pending_transactions

    txn = Transaction.model_validate(
        {
            "_id": "ptxn_1",
            "_account": "acc_chq_001",
            "date": "2026-05-22T00:00:00Z",
            "description": "PENDING - COFFEE",
            "amount": -5.50,
            "type": "EFTPOS",
        }
    )
    item = load_fixture("accounts")["items"][0]
    client = MagicMock()
    client.get_account = AsyncMock(return_value=Account.model_validate(item))
    client.get_account_pending_transactions = AsyncMock(return_value=[txn])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions(account_id="acc_chq_001")
    assert result["account_id"] == "acc_chq_001"
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["amount"] == "-$5.50"


async def test_account_pending_transactions_uses_account_currency(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pending txn amounts honour the parent account's currency (e.g. Wise USD)."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.models import Transaction
    from nz_akahu_mcp.tools.accounts import get_pending_transactions

    txn = Transaction.model_validate(
        {
            "_id": "ptxn_usd",
            "_account": "acc_wise_usd",
            "date": "2026-05-22T00:00:00Z",
            "description": "PENDING - SUBSCRIPTION",
            "amount": -9.99,
            "type": "PAYMENT",
        }
    )
    item = {**load_fixture("accounts")["items"][0], "balance": {
        "currency": "USD",
        "current": 100.00,
        "available": 100.00,
        "limit": 0,
        "overdrawn": False,
    }}
    client = MagicMock()
    client.get_account = AsyncMock(return_value=Account.model_validate(item))
    client.get_account_pending_transactions = AsyncMock(return_value=[txn])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions(account_id="acc_wise_usd")
    assert result["transactions"][0]["amount"] == "-USD 9.99"


async def test_account_pending_transactions_no_balance_defaults_to_nzd(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the parent account has no balance block, fall back to NZD formatting."""
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.models import Transaction
    from nz_akahu_mcp.tools.accounts import get_pending_transactions

    txn = Transaction.model_validate(
        {
            "_id": "ptxn_nobal",
            "_account": "acc_x",
            "date": "2026-05-22T00:00:00Z",
            "description": "PENDING",
            "amount": -1.00,
            "type": "EFTPOS",
        }
    )
    item = {**load_fixture("accounts")["items"][0], "balance": None}
    client = MagicMock()
    client.get_account = AsyncMock(return_value=Account.model_validate(item))
    client.get_account_pending_transactions = AsyncMock(return_value=[txn])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions(account_id="acc_x")
    assert result["transactions"][0]["amount"] == "-$1.00"


async def test_account_pending_transactions_empty(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.accounts import get_pending_transactions

    item = load_fixture("accounts")["items"][0]
    client = MagicMock()
    client.get_account = AsyncMock(return_value=Account.model_validate(item))
    client.get_account_pending_transactions = AsyncMock(return_value=[])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions(account_id="acc_chq_001")
    assert result["transactions"] == []


async def test_server_registers_six_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.accounts import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "list_accounts",
        "get_account",
        "get_account_balance",
        "refresh_all_accounts",
        "refresh_account",
        "get_pending_transactions",
    }
