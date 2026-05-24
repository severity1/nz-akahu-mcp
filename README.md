# nz-akahu-mcp

Unofficial MCP server for the [Akahu](https://akahu.nz) open-finance API
(New Zealand). Bring your own Akahu credentials; run locally over stdio; no
hosted backend.

- **23 tools** covering every user-scoped Akahu endpoint: account & balance reads, settled & pending transaction reads, batch lookup by id, spending insights, recurring detection, cash-flow forecasting, identity read, refresh writes, support-ticket writes, name verification.
- **Read-only by default.** All write tools refuse until you flip a flag.
- **Per-call consent for every write.** Even with writes enabled, Claude asks you to confirm each one.
- **Personal Apps only.** Payments and webhooks are full-app features and are out of scope for v1.

## Prerequisites

1. **Akahu Personal App + User token** - register at https://my.akahu.nz/developers
2. **[`uv`](https://docs.astral.sh/uv/)** for the `uvx` runner (or pip with a virtualenv)
3. **[Claude Code](https://docs.claude.com/en/docs/claude-code/overview)** or **[Claude Desktop](https://claude.ai/download)**

Set your tokens once in your shell (or write them into the `claude mcp add` / config-file commands below):

```bash
export AKAHU_APP_TOKEN="app_token_..."
export AKAHU_USER_TOKEN="user_token_..."
# Optional - everything below is the default:
export AKAHU_READ_ONLY=true
export AKAHU_AUTOMATION_BYPASS=false
```

## Install in Claude Code

Pick whichever fits your situation.

### Option A: from the Severity1 marketplace (one command, recommended)

```bash
# In a Claude Code session:
/plugin marketplace add severity1/severity1-marketplace
/plugin install nz-akahu-mcp@severity1
```

This installs the plugin, which contributes both:
- The `nz-akahu` MCP server (all 23 tools)
- The bundled `nz-akahu` skill (NZ banking context, advice boundaries, write-mode safety guidance)

To enable the plugin in the current project, run `/plugin` and toggle it on.

> **For the marketplace owner:** add the entry from `examples/marketplace-entry.json` to `.claude-plugin/marketplace.json` in `severity1/severity1-marketplace` so the install command above resolves.

### Option B: remote install via `claude mcp add` (without the marketplace)

Once published to PyPI:

```bash
claude mcp add nz-akahu \
  --scope user \
  --env AKAHU_APP_TOKEN=app_token_... \
  --env AKAHU_USER_TOKEN=user_token_... \
  --env AKAHU_READ_ONLY=true \
  -- uvx nz-akahu-mcp
```

Before a PyPI release, install straight from GitHub:

```bash
claude mcp add nz-akahu \
  --scope user \
  --env AKAHU_APP_TOKEN=app_token_... \
  --env AKAHU_USER_TOKEN=user_token_... \
  -- uvx --from git+https://github.com/severity1/nz-akahu-mcp nz-akahu-mcp
```

Scope options:
- `--scope user` - available in every Claude Code project for your user (recommended for personal banking data)
- `--scope project` - shared via `.mcp.json` checked into the repo (don't use this for tokens)
- `--scope local` - this project only, not shared (default)

### Option C: local install via `claude mcp add` (clone + dev loop)

If you want to hack on the server:

```bash
git clone https://github.com/severity1/nz-akahu-mcp.git
cd nz-akahu-mcp
uv sync --extra dev
uv run pytest         # 166 tests, 100% line + branch coverage

# Wire the local checkout into Claude Code:
claude mcp add nz-akahu \
  --scope user \
  --env AKAHU_APP_TOKEN=app_token_... \
  --env AKAHU_USER_TOKEN=user_token_... \
  -- uv --directory "$(pwd)" run nz-akahu-mcp
```

After editing source, restart your Claude Code session - the next tool call picks up the new code.

### Option D: pip install from PyPI

For users on machines without `uv`, or in environments where only `pip` is approved. Install into a virtualenv so you don't pollute system Python:

```bash
python -m venv ~/.venvs/nz-akahu-mcp
source ~/.venvs/nz-akahu-mcp/bin/activate   # Windows: ~/.venvs/nz-akahu-mcp/Scripts/activate
pip install nz-akahu-mcp
```

Then point Claude Code at the installed console script (note the absolute path so it works from any working directory):

```bash
claude mcp add nz-akahu \
  --scope user \
  --env AKAHU_APP_TOKEN=app_token_... \
  --env AKAHU_USER_TOKEN=user_token_... \
  -- ~/.venvs/nz-akahu-mcp/bin/nz-akahu-mcp
```

To upgrade later: `~/.venvs/nz-akahu-mcp/bin/pip install --upgrade nz-akahu-mcp` and restart Claude Code.

### Verify the install

```bash
claude mcp list                # confirms 'nz-akahu' is registered
claude mcp get nz-akahu        # shows the resolved command and env
```

Inside Claude Code, ask: *"What accounts do I have?"* - it should call `nz-akahu_accounts_list_accounts` and return masked account details.

## Install in Claude Desktop

Copy `examples/claude_desktop_config.json` into your Claude Desktop config and replace the placeholders. The config lives at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

Then restart Claude Desktop.

## Run standalone (no client)

Useful for debugging:

```bash
# Via uvx (zero-install):
uvx nz-akahu-mcp

# Via pip (after `pip install nz-akahu-mcp` in your venv):
nz-akahu-mcp

# From a local checkout:
uv run nz-akahu-mcp
```

The server speaks MCP over stdio. The FastMCP inspector is handy:

```bash
uv run fastmcp dev src/nz_akahu_mcp/server.py
```

## Architecture

```
+--- root FastMCP server (server.py) -------------------------+
| mounts 5 sub-servers, prints safety banner on startup       |
+----+---------+---------+---------+---------+----------------+
     |         |         |         |         |
   accounts  transactions insights planning  identity
     |         |         |         |         |
     +--------- AkahuClient (httpx + retry) -+
                          |
                          v
                  https://api.akahu.io/v1
                  (dual-header auth)
```

Safety lives in `safety.py` as the `@require_write_consent` decorator on every
write tool. `rg "@require_write_consent"` enumerates writes.
`rg "automatable=True"` enumerates the bypass-eligible subset.

## Read-only by default

The server starts with `AKAHU_READ_ONLY=true`. Every write tool refuses with
this message:

> Write operations are disabled. To enable: set `AKAHU_READ_ONLY=false` in your
> `.env` and restart the MCP server. Each write will require your explicit
> confirmation through Claude (or set `AKAHU_AUTOMATION_BYPASS=true` for the
> automatable subset only).

When writes ARE enabled, every write still calls `ctx.elicit()` to ask you in
Claude's UI before firing.

### Automation bypass (advanced)

If you're running unattended automation (e.g. a nightly cron that refreshes
balances), per-call elicitation gets in the way. Setting
`AKAHU_AUTOMATION_BYPASS=true` *together with* `AKAHU_READ_ONLY=false` skips the
elicit prompt for the **automatable subset only**:

| Tool                                | Bypass-eligible? | Why                                                                          |
| ----------------------------------- | ----------------- | ---------------------------------------------------------------------------- |
| `accounts/refresh_all_accounts`     | YES               | Idempotent, rate-limited, real automation use case                           |
| `accounts/refresh_account`          | YES               | Same                                                                         |
| `transactions/report_transaction_issue` | NO            | Sends ticket to a human at Akahu support; never auto                         |

**Recommendation:** leave this OFF for ad-hoc Claude conversations. Only set it
on if you're scripting refresh cycles. Each bypassed call logs at INFO with the
tool name; the server prints a banner on startup listing the bypass-eligible
tools so the current posture is always visible.

If you set `AKAHU_AUTOMATION_BYPASS=true` together with `AKAHU_READ_ONLY=true`,
the server refuses to start - the combination is incoherent (writes are off, so
there's nothing to bypass).

## Tool reference

### Read tools (19)

**`accounts/`**
- `list_accounts` - all connected accounts (masked, formatted balances)
- `get_account(account_id)` - single account details
- `get_account_balance(account_id)` - balance only
- `get_pending_transactions(account_id)` - not-yet-settled debits/credits for one account

**`transactions/`**
- `get_transactions(account_id?, start_date?, end_date?, category?, min_amount?, max_amount?, limit=100)`
- `get_transaction(transaction_id)`
- `get_transactions_by_ids(ids)` - batch fetch by Akahu txn id (useful for webhook follow-up)
- `get_pending_transactions` - not-yet-settled across all accounts
- `search_transactions(query, limit=50)` - substring across description + merchant.name

**`insights/`**
- `analyse_spending(start_date, end_date, group_by="category"|"merchant"|"account")`
- `find_recurring_payments(lookback_days=90)` - two-tier HIGH/MEDIUM confidence
- `cash_flow_summary(start_date, end_date)` - inflows, outflows, net, HIGH-only fixed
- `compare_periods(period_a_start, period_a_end, period_b_start, period_b_end)`
- `top_merchants(start_date, end_date, limit=10)`
- `detect_unusual_transactions(lookback_days=30, threshold_multiplier=3.0)` - per-category median + MAD

**`planning/`**
- `project_balance(account_id, days_ahead=30)` - linear extrapolation
- `upcoming_recurring(days_ahead=30)` - forecasts both HIGH and MEDIUM
- `savings_capacity(lookback_days=90)` - monthly inflows minus HIGH fixed outflows

**`identity/`**
- `get_me`

### Write tools (4)

- `accounts/refresh_all_accounts` *(bypass-eligible)*
- `accounts/refresh_account(account_id)` *(bypass-eligible)*
- `transactions/report_transaction_issue(transaction_id, issue_type, fields?, comment?, other_transaction_id?)` *(always elicits)*
- `identity/verify_name(family_name, given_name?, middle_name?, initials?, account_id?)` *(always elicits)* - requires Personal-App scope grant; without it Akahu returns 403

## Privacy & security

- Account numbers are masked: `01-1234-1234567-00` -> `01-****-***4567-00`.
- Tokens are never logged. The DEBUG-level body log is response-only.
- All filters are applied client-side after the API call returns. Akahu has no field-level access control for Personal Apps.
- The server runs entirely on your machine. The only outbound traffic is to `https://api.akahu.io/v1`.

## Personal Apps only

This server uses the Akahu Personal App model (per-user OAuth). Per the
[Akahu authentication docs](https://developers.akahu.nz/reference/api-akahu-io-authentication#app-scoped-endpoints):

> App-scoped endpoints are not available to Personal Apps.

That puts the following Akahu endpoints permanently out of scope for v1 and
they are not exposed as tools (they would always 4xx):

- `/categories` - NZFCC category taxonomy (transactions carry their category inline so this rarely matters)
- `/connections` - supported-bank list
- `/identity/{id}/verify-name` - name-against-account verification (the user-scoped `/verify/name` is exposed instead via `identity/verify_name`)

Full-app features are also out of scope for v1:

- Payments (`make_payment`, `cancel_payment`, etc.)
- Webhooks (`subscribe_webhook`, etc.)

These are tracked for a hypothetical v2.

### Scope-grant gotchas

Two endpoints in the user-scoped surface require a Personal-App scope you can
toggle at https://my.akahu.nz/developers. Without the grant, Akahu returns 403:

- `GET /parties` - counterparty list (we DON'T ship a tool for this since it's
  consistently 403 on Personal Apps; flag if you want it added)
- `POST /verify/name` and `POST /verify/name/{id}` - we ship these as
  `identity/verify_name`. If you see "Forbidden" responses, enable the relevant
  identity scope on your Personal App and try again.

## Releasing

PyPI publishes are automated via GitHub Actions using Trusted Publishing
(OIDC) - no API tokens in repo secrets. To cut a release: bump
`version` in `pyproject.toml`, push a `vX.Y.Z` tag, then publish a
GitHub Release with that tag. The workflow runs the full test+ruff+mypy
gate, asserts the pyproject version matches the tag, and publishes to
PyPI.

See [`PUBLISHING.md`](PUBLISHING.md) for the one-time PyPI side setup
(pending publisher, `pypi` environment, optional approval rules) and the
manual-publish fallback.

## Disclaimer

This is an unofficial integration. Not affiliated with Akahu, your bank, or
any financial institution. Use at your own risk. The maintainers are not
responsible for any data loss, unauthorised access, or financial impact arising
from use of this software.

## License

Apache-2.0. See `LICENSE`.
