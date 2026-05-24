---
name: nz-akahu-mcp
description: Personal NZ banking assistant powered by Akahu open-finance data. Spending analysis, recurring detection, savings capacity. Read-by-default; writes require explicit confirmation.
---

# nz-akahu-mcp skill guide

This server gives Claude read access to a single user's New Zealand bank accounts
through Akahu (https://akahu.nz). It is **personal-app scoped** and intended for
the user themselves to ask about their own finances, not for advising others.

## Privacy defaults

- Account numbers are always masked in tool output (`01-****-***4567-00`).
- Tools return formatted NZD strings (`$1,234.56`) alongside raw floats so the LLM can do math without losing precision.
- Tokens never appear in logs.

## Date conventions

- Use Pacific/Auckland for any "today" / "yesterday" / "this month" reasoning unless the user says otherwise.
- Pass ISO 8601 timestamps to tools (e.g. `2026-05-01T00:00:00Z`).

## Tool-selection patterns

- **"What's in my account?"** -> `accounts/list_accounts`, then `accounts/get_account` for details.
- **"How much did I spend on groceries last month?"** -> `insights/analyse_spending(group_by="category")`.
- **"What subscriptions am I paying?"** -> `insights/find_recurring_payments`. Filter to `confidence == "HIGH"` for definite subscriptions; `MEDIUM` for variable bills like power.
- **"What can I save each month?"** -> `planning/savings_capacity` (uses HIGH-confidence fixed outflows only).
- **"What bills are coming up?"** -> `planning/upcoming_recurring`. Surfaces both HIGH and MEDIUM tagged.
- **"Is this transaction unusual?"** -> `insights/detect_unusual_transactions` (per-category median + MAD).
- **"Refresh my data"** -> `accounts/refresh_all_accounts` (requires write mode, see below).
- **"What's pending on my account?"** -> `accounts/get_pending_transactions(account_id)` or `transactions/get_pending_transactions` (across all accounts). Pending entries hit available balance immediately even before they settle.
- **"Look these up by id"** (e.g. from a webhook) -> `transactions/get_transactions_by_ids(ids=[...])`.
- **"Is my legal name on the bank file?"** -> `identity/verify_name(family_name, given_name?, account_id?)` (write tool, always elicits, requires Akahu identity scope grant).

## Advice boundaries

The skill is data + analysis, not financial advice. When the user asks "should I"
questions (should I switch banks, should I pay off X first, am I overspending),
present the data, surface the relevant tradeoffs, and let the user decide. If the
user appears in financial distress, mention NZ resources:

- **MoneyTalks** (free, confidential): 0800 345 123
- **Citizens Advice Bureau**: cab.org.nz
- **Sorted.org.nz** (financial literacy, owned by the Retirement Commission)

## Write mode

By default `AKAHU_READ_ONLY=true`. Write tools refuse with a clear error. To
enable writes, the user sets `AKAHU_READ_ONLY=false` and restarts the server.

When writes are enabled, every write tool elicits explicit confirmation from the
user before firing. There is one narrow opt-in: `AKAHU_AUTOMATION_BYPASS=true`
skips elicitation for the *automatable* subset (refresh tools only). The
non-automatable writes always elicit regardless:
- `report_transaction_issue` (sends a ticket to a human at Akahu support)
- `verify_name` (identity-sensitive; may incur a per-call bank charge)

See `references/write-mode-safety.md` for the elicitation copy for each tool and
the full bypass-eligibility table.

## NZ banking quirks

See `references/nz-banking-context.md` for:
- Particulars/code/reference fields and how they're used
- Automatic Payments (AP) vs Direct Debits (DD)
- KiwiSaver "classic" connections (slow-refresh accounts)
- The BB-bbbb-AAAAAAA-SS account-number format
