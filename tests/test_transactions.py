"""Tests for the transactions sub-server."""

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
    # iter_account_transactions mirrors iter_transactions but takes a positional
    # account_id. The fake just returns the same fixture - any per-account
    # filtering would be Akahu's job; the tool no longer filters client-side.
    client.iter_account_transactions = MagicMock(
        side_effect=lambda _account_id, **_: _async_iter(txns)
    )
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


async def test_get_transactions_with_account_id_routes_to_per_account_endpoint(
    fake_env: None, patched_client: MagicMock
) -> None:
    """When account_id is given, the tool must use iter_account_transactions
    (i.e. hit GET /accounts/{id}/transactions for server-side filtering) instead
    of pulling all txns and filtering client-side."""
    from nz_akahu_mcp.tools.transactions import get_transactions

    result = await get_transactions(
        account_id="acc_chq_001",
        start_date="2026-05-01T00:00:00Z",
        end_date="2026-05-31T23:59:59Z",
    )
    assert len(result["transactions"]) == 3  # the fixture returns 3 unfiltered
    patched_client.iter_account_transactions.assert_called_once()
    args, kwargs = patched_client.iter_account_transactions.call_args
    assert args[0] == "acc_chq_001"
    assert kwargs == {"start": "2026-05-01T00:00:00Z", "end": "2026-05-31T23:59:59Z"}
    # And the unfiltered iterator must NOT have been used.
    patched_client.iter_transactions.assert_not_called()


async def test_get_transactions_without_account_id_uses_all_txn_endpoint(
    fake_env: None, patched_client: MagicMock
) -> None:
    """When account_id is None, fall through to GET /transactions across all accounts."""
    from nz_akahu_mcp.tools.transactions import get_transactions

    await get_transactions(start_date="2026-05-01T00:00:00Z")
    patched_client.iter_transactions.assert_called_once_with(
        start="2026-05-01T00:00:00Z", end=None
    )
    patched_client.iter_account_transactions.assert_not_called()


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
    from nz_akahu_mcp.safety import ElicitationCancelledError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory(elicit_action="cancel")
    with pytest.raises(ElicitationCancelledError):
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


async def test_report_transaction_issue_duplicate_elicits_other_id(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    """When other_transaction_id is omitted, the tool prompts for it mid-call.

    Pattern: build ctx via ctx_factory(), then override ctx.elicit.side_effect
    with the sequence of results we want. First call is the safety
    confirmation (empty AcceptedElicitation), second is the typed value.
    """
    from fastmcp.server.elicitation import AcceptedElicitation

    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    ctx.elicit.side_effect = [
        AcceptedElicitation(data={}),
        AcceptedElicitation(data="txn_002"),
    ]
    result = await report_transaction_issue(
        ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
    )
    assert result["success"] is True
    assert ctx.elicit.await_count == 2
    _, kwargs = patched_client.report_transaction_issue.await_args
    assert kwargs["other_transaction_id"] == "txn_002"


async def test_report_transaction_issue_enrichment_elicits_fields(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from fastmcp.server.elicitation import AcceptedElicitation

    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    ctx.elicit.side_effect = [
        AcceptedElicitation(data={}),
        AcceptedElicitation(data=["merchant", "category"]),
    ]
    result = await report_transaction_issue(
        ctx=ctx, transaction_id="txn_001", issue_type="ENRICHMENT_ERROR"
    )
    assert result["success"] is True
    assert ctx.elicit.await_count == 2
    _, kwargs = patched_client.report_transaction_issue.await_args
    assert kwargs["fields"] == ["merchant", "category"]


async def test_report_transaction_issue_field_fill_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from fastmcp.server.elicitation import AcceptedElicitation, DeclinedElicitation

    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    ctx.elicit.side_effect = [
        AcceptedElicitation(data={}),
        DeclinedElicitation(),
    ]
    with pytest.raises(ElicitationDeclinedError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )
    patched_client.report_transaction_issue.assert_not_awaited()


async def test_report_transaction_issue_field_fill_cancel(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation

    from nz_akahu_mcp.safety import ElicitationCancelledError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    ctx.elicit.side_effect = [
        AcceptedElicitation(data={}),
        CancelledElicitation(),
    ]
    with pytest.raises(ElicitationCancelledError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="DUPLICATE"
        )
    patched_client.report_transaction_issue.assert_not_awaited()


async def test_report_transaction_issue_empty_fields_treated_as_decline(
    writable_env: None, ctx_factory: Callable[..., MagicMock], patched_client: MagicMock
) -> None:
    """An empty list payload from the user is effectively a decline; do not
    forward an empty fields=[] body to Akahu (it would 400)."""
    from fastmcp.server.elicitation import AcceptedElicitation

    from nz_akahu_mcp.safety import ElicitationDeclinedError
    from nz_akahu_mcp.tools.transactions import report_transaction_issue

    ctx = ctx_factory()
    ctx.elicit.side_effect = [
        AcceptedElicitation(data={}),
        AcceptedElicitation(data=[]),
    ]
    with pytest.raises(ElicitationDeclinedError):
        await report_transaction_issue(
            ctx=ctx, transaction_id="txn_001", issue_type="ENRICHMENT_ERROR"
        )
    patched_client.report_transaction_issue.assert_not_awaited()


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


# ---------- get_transactions_by_ids ----------


async def test_get_transactions_by_ids(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.transactions import get_transactions_by_ids

    client = MagicMock()
    client.get_transactions_by_ids = AsyncMock(return_value=_fake_txns())
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_transactions_by_ids(ids=["txn_001", "txn_002"])
    assert len(result["transactions"]) == 3
    client.get_transactions_by_ids.assert_awaited_once_with(["txn_001", "txn_002"])


# ---------- get_pending_transactions ----------


async def test_get_pending_transactions(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.transactions import get_pending_transactions

    client = MagicMock()
    client.get_pending_transactions = AsyncMock(return_value=_fake_txns())
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions()
    assert len(result["transactions"]) == 3


async def test_get_pending_transactions_empty(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nz_akahu_mcp import deps
    from nz_akahu_mcp.tools.transactions import get_pending_transactions

    client = MagicMock()
    client.get_pending_transactions = AsyncMock(return_value=[])
    monkeypatch.setattr(deps, "get_client", lambda: client)
    result = await get_pending_transactions()
    assert result["transactions"] == []


async def test_server_registers_six_tools(fake_env: None) -> None:
    from nz_akahu_mcp.tools.transactions import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "get_transactions",
        "get_transaction",
        "search_transactions",
        "report_transaction_issue",
        "get_transactions_by_ids",
        "get_pending_transactions",
    }
