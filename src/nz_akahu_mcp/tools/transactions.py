"""Transactions sub-server: 5 read tools + 1 write tool."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import Context, FastMCP

from nz_akahu_mcp import deps
from nz_akahu_mcp.formatting import format_money
from nz_akahu_mcp.models import Transaction
from nz_akahu_mcp.safety import (
    ElicitationDeclinedError,
    elicit_value,
    require_write_consent,
)

server: FastMCP[Any] = FastMCP("transactions")

IssueType = Literal["DUPLICATE", "ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"]
_VALID_ISSUE_TYPES: frozenset[str] = frozenset(
    {"DUPLICATE", "ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"}
)


def _summarise(txn: Transaction) -> dict[str, Any]:
    """Convert a Transaction into the LLM-facing dict shape.

    Amounts are formatted in NZD; Akahu's Transaction model does not carry a
    per-transaction currency. For multi-currency accounts, read the parent
    account's currency via `accounts/get_account(account_id)`.
    """
    return {
        "id": txn.id,
        "account_id": txn.account,
        "date": txn.date.date().isoformat(),
        "description": txn.description,
        "amount": format_money(txn.amount, "NZD"),
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
    """List settled transactions with optional filters.

    Returns {"transactions": [...]} where each entry has id, account_id,
    date (YYYY-MM-DD), description, amount (NZD-formatted string,
    e.g. "-$12.50"), amount_raw (float; negative = debit), type,
    merchant (str | None), category (str | None).

    Args:
        account_id: Scope to one account (server-side filter).
        start_date: ISO 8601 timestamp lower bound (server-side filter).
        end_date: ISO 8601 timestamp upper bound (server-side filter).
        category: Exact Category.name match (client-side filter).
        min_amount: Lower bound on signed amount (client-side; negatives are debits).
        max_amount: Upper bound on signed amount (client-side).
        limit: Max items returned (default 100).
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
    """Fetch one transaction by id.

    Returns the same shape as one entry in get_transactions["transactions"]:
    id, account_id, date, description, amount, amount_raw, type, merchant,
    category.

    Args:
        transaction_id: Akahu transaction id (e.g. "txn_a1b2c3").
    """
    txn = await deps.get_client().get_transaction(transaction_id)
    return _summarise(txn)


@server.tool
async def get_transactions_by_ids(ids: list[str]) -> dict[str, Any]:
    """Batch-fetch transactions by their ids in one request.

    Useful when you have a list of transaction ids (e.g. from a webhook or
    a prior query) and want to inspect them together. Returns
    {"transactions": [...]} with the same per-entry shape as get_transactions.

    Args:
        ids: List of Akahu transaction ids.
    """
    txns = await deps.get_client().get_transactions_by_ids(ids)
    return {"transactions": [_summarise(t) for t in txns]}


@server.tool
async def get_pending_transactions() -> dict[str, Any]:
    """List all pending (not-yet-settled) transactions across the user's accounts.

    Include in cash-flow projections. Pending transactions affect available
    balance immediately, but won't appear in get_transactions until they post.

    Returns:
        {"transactions": [...]} with id, account_id, date, description,
        amount (NZD-formatted), amount_raw, type, merchant, category.
    """
    txns = await deps.get_client().get_pending_transactions()
    return {"transactions": [_summarise(t) for t in txns]}


@server.tool
async def search_transactions(query: str, limit: int = 50) -> dict[str, Any]:
    """Case-insensitive substring search across description and merchant.name.

    Iterates all transactions until `limit` matches are found. Use for
    free-text lookups; prefer get_transactions when filtering by date,
    account, or amount. Returns {"transactions": [...]} with the same
    per-entry shape as get_transactions.

    Args:
        query: Substring to match (case-insensitive).
        limit: Max matches returned (default 50).
    """
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
    automatable=False,
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
    """Submit a support ticket about a transaction to Akahu staff.

    Sends a ticket to a human at Akahu support. Always elicits user
    confirmation (not bypass-eligible). issue_type validation:
      - "DUPLICATE": requires other_transaction_id (the paired duplicate).
      - "ENRICHMENT_ERROR": requires fields=[...] listing affected field names.
      - "ENRICHMENT_SUGGESTION": requires fields=[...] listing suggested fields.

    Returns {"success": bool, "message": str | None}.

    Args:
        transaction_id: Akahu transaction id the ticket is about.
        issue_type: One of "DUPLICATE", "ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION".
        fields: Affected field names; required for ENRICHMENT_* issue types.
            Omitted -> the user is prompted to supply them via elicitation.
        comment: Optional free-text context for the support agent.
        other_transaction_id: Paired transaction id; required for DUPLICATE.
            Omitted -> the user is prompted to supply it via elicitation.
    """
    if issue_type not in _VALID_ISSUE_TYPES:
        raise ValueError(
            f"invalid issue_type {issue_type!r}; must be one of {sorted(_VALID_ISSUE_TYPES)}"
        )
    if issue_type == "DUPLICATE" and not other_transaction_id:
        other_transaction_id = await elicit_value(
            ctx,
            "Provide the paired duplicate transaction id:",
            str,
        )
    if issue_type in {"ENRICHMENT_ERROR", "ENRICHMENT_SUGGESTION"} and not fields:
        fields = await elicit_value(
            ctx,
            f"List the affected field names for {issue_type} (e.g. merchant, category):",
            list[str],
        )
        if not fields:
            raise ElicitationDeclinedError("User provided no fields.")

    result = await deps.get_client().report_transaction_issue(
        transaction_id,
        issue_type=issue_type,
        fields=fields,
        comment=comment,
        other_transaction_id=other_transaction_id,
    )
    return {"success": result.success, "message": result.message}
