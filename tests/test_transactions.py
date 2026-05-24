"""Tests for the transactions sub-server: 3 read + 1 write (always elicits)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from nz_akahu_mcp.models import SupportRequest, Transaction
from tests.conftest import load_fixture


def _fake_txns() -> list[Transaction]:
    return [Transaction.model_validate(i) for i in load_fixture("transactions")["items"]]


def _async_iter(items: list[Transaction]) -> AsyncIterator[Transaction]:
    async def gen() -> AsyncIterator[Transaction]:
        for t in items:
            yield t

    return gen()


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from nz_akahu_mcp import deps

    client = MagicMock()
    txns = _fake_txns()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter(txns))
    client.get_transaction = AsyncMock(return_value=txns[0])
    client.report_transaction_issue = AsyncMock(return_value=SupportRequest(success=True))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    return client


# ---------- get_transactions ----------


async def test_get_transactions_returns_all(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions()
    assert len(result["transactions"]) == 3
    t0 = result["transactions"][0]
    assert t0["id"] == "txn_001"
    assert t0["amount"] == "-$82.45"
    assert t0["merchant"] == "Countdown"
    assert t0["category"] == "Groceries"


async def test_get_transactions_filters_by_amount(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(min_amount=0)  # only positive (income)
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["id"] == "txn_003"


async def test_get_transactions_filters_max_amount(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(max_amount=-89)  # only smaller-than-90 debits
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["id"] == "txn_002"


async def test_get_transactions_filters_by_category(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(category="Groceries")
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["category"] == "Groceries"


async def test_get_transactions_filters_by_account(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(account_id="acc_chq_001")
    assert len(result["transactions"]) == 3
    result_other = await get_transactions(account_id="acc_other_xxx")
    assert len(result_other["transactions"]) == 0


async def test_get_transactions_respects_limit(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(limit=2)
    assert len(result["transactions"]) == 2


async def test_get_transactions_handles_no_merchant_or_category(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.transactions import get_transactions

    plain = Transaction.model_validate(
        {
            "_id": "txn_x",
            "_account": "acc",
            "date": "2026-01-01T00:00:00Z",
            "description": "FOO",
            "amount": -10.00,
            "type": "EFTPOS",
        }
    )
    client = MagicMock()
    client.iter_transactions = MagicMock(side_effect=lambda **_: _async_iter([plain]))
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_transactions()
    assert result["transactions"][0]["merchant"] is None
    assert result["transactions"][0]["category"] is None


# ---------- get_transaction ----------


async def test_get_transaction_single(fake_env: None, patched_client: MagicMock) -> None:
    from nz_akahu_mcp.tools.transactions import get_transaction

    result = await get_transaction(transaction_id="txn_001")
    assert result["id"] == "txn_001"
    assert result["amount"] == "-$82.45"


# ---------- search_transactions ----------


async def test_search_transactions_by_description(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import search_transactions

    result = await search_transactions(query="spark")  # case-insensitive
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["id"] == "txn_002"


async def test_search_transactions_by_merchant(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import search_transactions

    result = await search_transactions(query="countdown")
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["merchant"] == "Countdown"


async def test_search_transactions_no_match(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import search_transactions

    result = await search_transactions(query="zzznever")
    assert result["transactions"] == []


async def test_search_transactions_respects_limit(
    fake_env: None, patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import search_transactions

    result = await search_transactions(query="", limit=2)  # empty query matches all
    assert len(result["transactions"]) == 2


# ---------- report_transaction_issue (write, NOT bypass-eligible) ----------


async def test_report_transaction_issue_blocks_in_readonly(
    fake_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ReadOnlyError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    with pytest.raises(ReadOnlyError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )


async def test_report_transaction_issue_accept(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    result = await report_transaction_issue(
        ctx=ctx,
        transaction_id="txn_001",
        issue_type="DUPLICATE",
        other_transaction_id="txn_002",
    )
    assert result["success"] is True
    patched_client.report_transaction_issue.assert_awaited_once()


async def test_report_transaction_issue_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="decline")
    with pytest.raises(ElicitationDeclinedError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )


async def test_report_transaction_issue_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationDeclinedError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )


async def test_report_transaction_issue_still_elicits_under_bypass(
    bypass_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    """This tool is NOT marked automatable, so bypass must not skip elicit."""
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    await report_transaction_issue(
        ctx=ctx,
        transaction_id="txn_001",
        issue_type="DUPLICATE",
        other_transaction_id="txn_002",
    )
    ctx.elicit.assert_awaited_once()


async def test_report_transaction_issue_validates_issue_type(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    with pytest.raises(ValueError, match="issue_type"):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="NOT_A_REAL_KIND"
        )


async def test_report_transaction_issue_duplicate_requires_other(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    with pytest.raises(ValueError, match="other_transaction_id"):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )


async def test_report_transaction_issue_enrichment_requires_fields(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    with pytest.raises(ValueError, match="fields"):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="ENRICHMENT_ERROR"
        )


async def test_report_transaction_issue_enrichment_suggestion_ok(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="accept")
    result = await report_transaction_issue(
        ctx=ctx,
        transaction_id="txn_001",
        issue_type="ENRICHMENT_SUGGESTION",
        fields=["merchant"],
        comment="Should be 'Woolworths NZ' now",
    )
    assert result["success"] is True


async def test_server_registers_four_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.transactions import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "get_transactions",
        "get_transaction",
        "search_transactions",
        "report_transaction_issue",
    }
