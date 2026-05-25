# nz-akahu-mcp

Unofficial MCP server for the [Akahu](https://akahu.nz) open-finance API
(New Zealand). Bring your own Akahu credentials; run locally over stdio; no
hosted backend.

- **14 tools.** Account & balance reads, settled & pending transaction reads, batch lookup by id, identity read, refresh writes, support-ticket writes, name verification.
- **Read-only by default.** Every write tool refuses until `AKAHU_READ_ONLY=false`.
- **Per-call consent for every write.** Each write calls `ctx.elicit()` for confirmation in the client.
- **Personal Apps only.** App-scoped endpoints, payments, and webhooks are not exposed.

## Prerequisites

1. **Akahu Personal App + User token** - register at https://my.akahu.nz/developers
2. **[`uv`](https://docs.astral.sh/uv/)** for the `uvx` runner (or pip with a virtualenv)
3. **[Claude Code](https://docs.claude.com/en/docs/claude-code/overview)** or **[Claude Desktop](https://claude.ai/download)**

The recommended install path below (marketplace plugin) prompts for your tokens and stores them in your OS keychain. Only the manual paths further down need shell env vars:

```bash
export AKAHU_APP_TOKEN="app_token_..."
export AKAHU_USER_TOKEN="user_token_..."
# Optional - everything below is the default:
export AKAHU_READ_ONLY=true
export AKAHU_AUTOMATION_BYPASS=false
```

## Install via Claude marketplace plugin (recommended)

Works in **both Claude Code and Claude Desktop**. Tokens prompt at install and are stored in your OS keychain (macOS Keychain on macOS, Windows Credential Manager on Windows). No shell env or `.env` file required; the package stays unchanged on PyPI.

**Claude Code (v2.1.83 or later):**

```text
/plugin marketplace add severity1/severity1-marketplace
/plugin install nz-akahu-mcp@severity1-marketplace
```

**Claude Desktop:** Cowork -> Plugins -> Add marketplace -> `severity1/severity1-marketplace` -> Install `nz-akahu-mcp`.

> **Known issue (May 2026):** Claude Desktop's install-time prompt for `userConfig` values may not fire ([anthropics/claude-code#39827](https://github.com/anthropics/claude-code/issues/39827), [#39455](https://github.com/anthropics/claude-code/issues/39455)). Workaround: after install, click the installed plugin and use **Configure options** to set the four values. Claude Code's CLI install prompt works correctly.

After install, `/mcp` should show `nz-akahu-mcp` connected. See [`plugin/README.md`](plugin/README.md) for the configure / reconfigure / uninstall flow and the full table of prompted values.

## Install in Claude Code (manual)

> **Prefer the [marketplace plugin path](#install-via-claude-marketplace-plugin-recommended) above.** The manual options below exist for users hacking on the server source, pinning a specific git ref, or running in environments without marketplace access. They all require you to manage tokens via shell env vars or `--env` flags.

### Option A: remote install via `claude mcp add`

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

### Option B: local install via `claude mcp add` (clone + dev loop)

If you want to hack on the server:

```bash
git clone https://github.com/severity1/nz-akahu-mcp.git
cd nz-akahu-mcp
uv sync --extra dev
uv run pytest         # 151 tests, 100% line + branch coverage

# Wire the local checkout into Claude Code:
claude mcp add nz-akahu \
  --scope user \
  --env AKAHU_APP_TOKEN=app_token_... \
  --env AKAHU_USER_TOKEN=user_token_... \
  -- uv --directory "$(pwd)" run nz-akahu-mcp
```

Restart your Claude Code session after editing source.

### Option C: pip install from PyPI

Install into a virtualenv:

```bash
python -m venv ~/.venvs/nz-akahu-mcp
source ~/.venvs/nz-akahu-mcp/bin/activate   # Windows: ~/.venvs/nz-akahu-mcp/Scripts/activate
pip install nz-akahu-mcp
```

Then point Claude Code at the installed console script (use the absolute path):

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

## Install in Claude Desktop (manual)

> **Prefer the [marketplace plugin path](#install-via-claude-marketplace-plugin-recommended) above** - it works in Claude Desktop too, prompts for your tokens at install, and stores them in your OS keychain. Use this manual path only if you can't reach the marketplace or specifically want to hand-edit `claude_desktop_config.json`.

Copy `examples/claude_desktop_config.json` into your Claude Desktop config and replace the placeholders. The config lives at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

Then restart Claude Desktop.

## Run standalone (no client)

```bash
# Via uvx (zero-install):
uvx nz-akahu-mcp

# Via pip (after `pip install nz-akahu-mcp` in your venv):
nz-akahu-mcp

# From a local checkout:
uv run nz-akahu-mcp
```

The server speaks MCP over stdio. Inspect tool calls with:

```bash
uv run fastmcp dev src/nz_akahu_mcp/server.py
```

## Architecture

```
+--- root FastMCP server (server.py) -----------+
| mounts 3 sub-servers, prints safety banner    |
+----+---------------+--------------+-----------+
     |               |              |
   accounts      transactions    identity
     |               |              |
     +----- AkahuClient (httpx + retry) ----+
                          |
                          v
                  https://api.akahu.io/v1
                  (dual-header auth)
```

Every write tool is decorated with `@require_write_consent` from `safety.py`.
`rg "@require_write_consent"` enumerates writes; `rg "automatable=True"`
enumerates the bypass-eligible subset.

## Read-only by default

The server starts with `AKAHU_READ_ONLY=true`. Every write tool refuses with
this message:

> Write operations are disabled. To enable: set `AKAHU_READ_ONLY=false` in your
> `.env` and restart the MCP server. Each write will require your explicit
> confirmation through Claude (or set `AKAHU_AUTOMATION_BYPASS=true` for the
> automatable subset only).

When writes ARE enabled, every write still calls `ctx.elicit()` to ask you in
Claude's UI before firing.

### Automation bypass

Setting `AKAHU_AUTOMATION_BYPASS=true` *together with* `AKAHU_READ_ONLY=false`
skips the elicit prompt for tools marked `automatable=True`:

| Tool                                    | Bypass-eligible? |
| --------------------------------------- | ---------------- |
| `accounts/refresh_all_accounts`         | YES              |
| `accounts/refresh_account`              | YES              |
| `transactions/report_transaction_issue` | NO               |
| `identity/verify_name`                  | NO               |

Each bypassed call logs at INFO with the tool name. The server prints a startup
banner listing the bypass-eligible tools.

Setting `AKAHU_AUTOMATION_BYPASS=true` with `AKAHU_READ_ONLY=true` is rejected
at startup.

## Tool reference

### Read tools (10)

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

This server uses the Akahu Personal App model (per-user OAuth). The following
endpoints are not exposed because they are
[app-scoped](https://developers.akahu.nz/reference/api-akahu-io-authentication#app-scoped-endpoints)
and unreachable from a Personal App:

- `/categories` - NZFCC category taxonomy (transactions carry their category inline)
- `/connections` - supported-bank list
- `/identity/{id}/verify-name` - app-scoped variant; use `identity/verify_name` instead

Full-app features are also out of scope:

- Payments (`make_payment`, `cancel_payment`, etc.)
- Webhooks (`subscribe_webhook`, etc.)

### Scope-grant gotchas

These user-scoped endpoints require a Personal-App scope toggled at
https://my.akahu.nz/developers; without the grant they return 403:

- `GET /parties` - counterparty list (not shipped as a tool)
- `POST /verify/name` and `POST /verify/name/{id}` - shipped as `identity/verify_name`

## Releasing

To cut a release: bump `version` in `pyproject.toml`, push a `vX.Y.Z` tag, then
publish a GitHub Release with that tag. The workflow runs the test+ruff+mypy
gate, asserts the pyproject version matches the tag, and publishes to PyPI via
Trusted Publishing (OIDC).

See [`PUBLISHING.md`](PUBLISHING.md) for the one-time PyPI setup and the
manual-publish fallback.

## Disclaimer

This is an unofficial integration. Not affiliated with Akahu, your bank, or
any financial institution. Use at your own risk. The maintainers are not
responsible for any data loss, unauthorised access, or financial impact arising
from use of this software.

## License

Apache-2.0. See `LICENSE`.
