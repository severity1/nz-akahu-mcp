# NZ banking context

## Account-number format

`BB-bbbb-AAAAAAA-SS` where:
- `BB` (2 digits): bank code (01 = ANZ, 02 = BNZ, 03 = Westpac, 06 = ASB, 12 = ASB old, 38 = Kiwibank, 11 = ASB/Bank of NZ historical)
- `bbbb` (4 digits): branch number
- `AAAAAAA` (7 digits): account number
- `SS` (2-3 digits): suffix (account type indicator, e.g. 00 = cheque, 50 = savings)

Our `mask_account` keeps the bank, the last 4 of the account, and the suffix - enough to disambiguate the user's own accounts without exposing the full string.

## Particulars / Code / Reference

NZ payments use three free-text fields the payer fills in:
- **Particulars**: usually the payer's name or a category label.
- **Code**: usually a customer number or invoice id.
- **Reference**: usually a short note (e.g. "RENT", "May 2026").

Akahu surfaces these under `transaction.meta`. They are *not* the same as the description; descriptions are merchant-supplied (often EFTPOS terminal text).

## Automatic Payments (AP) vs Direct Debits (DD)

- **AP**: payer-initiated, fixed amount, payer sets it up via bank.
- **DD**: payee-initiated (e.g. utility companies), amount can vary, payer pre-authorises the company to pull.

This matters for `find_recurring_payments`: APs are typically HIGH confidence (fixed amount), DDs often MEDIUM (variable bills).

## KiwiSaver

KiwiSaver providers connect through "classic" Akahu connections that refresh slowly (often once per day). `refresh_account` on a KiwiSaver account may return success but the data won't update faster than the provider allows.

## NZFCC categories

Akahu enriches transactions against the New Zealand Financial Capability Categories (NZFCC) reference. `list_categories` exposes the full taxonomy. The `personal_finance` group is the user-facing grouping (Bills / Food / Lifestyle / etc.); other groups (`merchant`, `industry`) exist for more specialised use cases.
