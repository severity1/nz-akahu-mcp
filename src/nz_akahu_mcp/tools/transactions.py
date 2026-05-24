"""Transactions sub-server: 3 read tools + 1 write tool (always elicits)."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import Context, FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.formatting import format_nzd
from nz_akahu_mcp.models import Transaction
from nz_akahu_mcp.safety import require_write_consent

server: FastMCP[Any] = FastMCP("transactions")

IssueType = Literal["DUPLICATE", "ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"]
_VALID_ISSUE_TYPES: frozenset[str] = frozenset(
    {"DUPLICATE", "ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"}
)


def _summarise(txn: Transaction) -> dict[str, Any]:
    """Convert a Transaction into the LLM-facing dict shape."""
    return {
        "id": txn.id,
        "account_id": txn.account,
        "date": txn.date.date().isoformat(),
        "description": txn.description,
        "amount": format_nzd(txn.amount),
        "amount_raw": txn.amount,
        "type": txn.type,
        "merchant": txn.merchant.name if txn.merchant else None,
        "category": txn.category.name if txn.category else None,
    }


@server.tool
async def get_transactions(
    account_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List transactions with optional filters.

    start_date and end_date are ISO 8601 timestamps the Akahu API filters server-side.
    account_id is also pushed server-side via GET /accounts/{id}/transactions when
    provided (saves transferring data for the user's other accounts). category,
    min_amount, and max_amount are filtered client-side.
    """
    client = deps.get_client()
    if account_id is not None:
        iterator = client.iter_account_transactions(
            account_id, start=start_date, end=end_date
        )
    else:
        iterator = client.iter_transactions(start=start_date, end=end_date)

    collected: list[Transaction] = []
    async for txn in iterator:
        if category and (txn.category is None or txn.category.name != category):
            continue
        if min_amount is not None and txn.amount < min_amount:
            continue
        if max_amount is not None and txn.amount > max_amount:
            continue
        collected.append(txn)
        if len(collected) >= limit:
            break
    return {"transactions": [_summarise(t) for t in collected]}


@server.tool
async def get_transaction(transaction_id: str) -> dict[str, Any]:
    """Fetch one transaction by id."""
    txn = await deps.get_client().get_transaction(transaction_id)
    return _summarise(txn)


@server.tool
async def get_transactions_by_ids(ids: list[str]) -> dict[str, Any]:
    """Batch-fetch transactions by their ids (POST /transactions/ids).

    Useful when a webhook delivers a list of changed transaction identifiers,
    or when an LLM has accumulated several txn ids it wants to inspect together.
    """
    txns = await deps.get_client().get_transactions_by_ids(ids)
    return {"transactions": [_summarise(t) for t in txns]}


@server.tool
async def get_pending_transactions() -> dict[str, Any]:
    """List all pending (not-yet-settled) transactions across the user's accounts.

    Pending transactions affect your available balance even though they haven't
    posted yet -- include these in cash-flow projections for near-term accuracy.
    """
    txns = await deps.get_client().get_pending_transactions()
    return {"transactions": [_summarise(t) for t in txns]}


@server.tool
async def search_transactions(query: str, limit: int = 50) -> dict[str, Any]:
    """Case-insensitive substring search across description and merchant.name."""
    needle = query.lower()
    matches: list[Transaction] = []
    async for txn in deps.get_client().iter_transactions():
        haystack = txn.description.lower()
        if txn.merchant:
            haystack += " " + txn.merchant.name.lower()
        if needle in haystack:
            matches.append(txn)
            if len(matches) >= limit:
                break
    return {"transactions": [_summarise(t) for t in matches]}


@server.tool
@require_write_consent(
    "Report an issue with transaction {transaction_id} to Akahu support staff. "
    "Issue type: {issue_type}.",
    automatable=False,  # explicit: not bypassable -- sends a ticket to a human.
)
async def report_transaction_issue(
    *,
    ctx: Context,
    transaction_id: str,
    issue_type: str,
    fields: list[str] | None = None,
    comment: str | None = None,
    other_transaction_id: str | None = None,
) -> dict[str, Any]:
    """Submit a support ticket about a transaction (duplicate or enrichment problem)."""
    if issue_type not in _VALID_ISSUE_TYPES:
        raise ValueError(
            f"invalid issue_type {issue_type!r}; must be one of {sorted(_VALID_ISSUE_TYPES)}"
        )
    if issue_type == "DUPLICATE" and not other_transaction_id:
        raise ValueError(
            "issue_type=DUPLICATE requires other_transaction_id to identify the pair."
        )
    if issue_type in {"ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"} and not fields:
        raise ValueError(
            f"issue_type={issue_type} requires fields=[...] listing the affected fields."
        )

    result = await deps.get_client().report_transaction_issue(
        transaction_id,
        issue_type=issue_type,
        fields=fields,
        comment=comment,
        other_transaction_id=other_transaction_id,
    )
    return {"success": result.success, "message": result.message}
