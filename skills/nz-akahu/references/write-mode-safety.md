# Write-mode safety reference

## Three layers, in order

1. **Read-only by default**. `AKAHU_READ_ONLY=true` (the default) makes every
   write tool refuse before any HTTP call, with a message naming the env vars
   needed to enable writes.

2. **Per-call elicitation**. When writes are enabled, every write tool calls
   `ctx.elicit()` with a clear "Confirm: ..." prompt. The user accepts, declines,
   or cancels in Claude's UI. Decline/Cancel raises `ElicitationDeclinedError`
   and no HTTP call is made.

3. **Structural separation by decorator**. Every write carries
   `@require_write_consent(...)`. Reviewers can `rg "@require_write_consent"` to
   enumerate writes, and `rg "automatable=True"` to enumerate the bypass-eligible
   subset.

## Bypass-eligibility table

| Tool                                | Automatable | Reason                                                                              |
| ----------------------------------- | ----------- | ----------------------------------------------------------------------------------- |
| `accounts/refresh_all_accounts`     | YES         | Idempotent; rate-limited by bank; common nightly-cron use case                      |
| `accounts/refresh_account`          | YES         | Idempotent; rate-limited; common targeted-refresh use case                          |
| `transactions/report_transaction_issue` | NO     | Sends a ticket to a human at Akahu support; mass automation would be spam          |
| `identity/verify_name`              | NO          | May incur a per-call charge from the bank; identity-sensitive operation             |

## Bypass criteria (the four-test gate)

A write tool may be marked `automatable=True` only if it satisfies ALL of:

1. **Idempotent or naturally rate-limited** - repeated calls don't compound damage.
2. **No third-party side effects** - doesn't notify external humans, doesn't move money, doesn't change identity records.
3. **Easily reversed or refreshed** - if triggered erroneously, state can be restored or it'll self-correct next cycle.
4. **Common automation use case exists** - users have a real reason to script it (e.g. nightly refresh), not just convenience.

Adding `automatable=True` to a future write tool must be justified inline with a code comment citing all four criteria.

## Configuration matrix

| READ_ONLY | AUTOMATION_BYPASS | Result                                                                                    |
| --------- | ----------------- | ----------------------------------------------------------------------------------------- |
| true      | false (default)   | All writes refuse with `ReadOnlyError`                                                    |
| true      | true              | **Server refuses to start** (incoherent combination, validated by config)                  |
| false     | false             | Every write elicits confirmation                                                          |
| false     | true              | Automatable writes skip elicit (logged INFO `[BYPASS]`); non-automatable still elicit     |

The startup banner makes the current posture visible every time the server boots.

## Elicitation copy per tool

- `accounts/refresh_all_accounts` -> "Refresh data for all your connected accounts. This is rate-limited by your bank."
- `accounts/refresh_account` -> "Refresh data for account {account_id}. Rate-limited by your bank."
- `transactions/report_transaction_issue` -> "Report an issue with transaction {transaction_id} to Akahu support staff. Issue type: {issue_type}."
- `identity/verify_name` -> "Verify the name '{name}' against account {account_id}. This sends an identity check to your bank and may incur a per-call charge."

## What each write actually does

- **refresh_*** -> Akahu queues a re-fetch of balances/transactions from the bank. Subject to rate limits set by the bank, not by Akahu.
- **report_transaction_issue** -> creates a support ticket visible to Akahu staff. Used for enrichment corrections (wrong merchant, wrong category) or duplicate detection.
- **verify_name** -> asks the bank to confirm whether a given name matches the account holder's records. Used for AML/payee verification. **Some banks charge per call.**
