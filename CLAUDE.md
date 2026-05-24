# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Unofficial MCP server for the Akahu open-finance API (NZ). Ships **14 tools** as
thin wrappers over Akahu Personal-App endpoints, distributed via PyPI as
`nz-akahu-mcp`. Runs locally over stdio; no hosted backend.

Design line: **primitives only.** Analytical questions ("what did I spend on
groceries?", "which subscriptions am I paying?") are the LLM's job over raw
transaction data. Don't add analytical/forecasting tools; the project removed
9 of those in v0.1.0 and shouldn't grow them back.

## Commands

All commands use `uv`.

```bash
uv sync --extra dev                    # install incl. dev deps
uv run pytest                          # full suite, 100% line+branch coverage gate
uv run pytest tests/test_accounts.py::test_list_accounts_returns_masked  # one test
uv run pytest -k "currency"            # filter by name
uv run ruff check .                    # lint (must be clean)
uv run mypy src                        # strict-mode type check (must be clean)
uv build                               # sdist + wheel into dist/
uv run nz-akahu-mcp                    # run server over stdio from local checkout
uv run fastmcp dev src/nz_akahu_mcp/server.py  # FastMCP inspector
```

The pytest config (`pyproject.toml [tool.pytest.ini_options]`) enforces
`--cov-fail-under=100` on **line AND branch** coverage. Any patch that drops
coverage below 100% fails the build. Mypy runs in `strict` mode.

## Architecture

```
src/nz_akahu_mcp/
├── server.py        Root FastMCP server; mounts 3 sub-servers under namespaces
├── tools/
│   ├── accounts.py        6 tools (4 read, 2 write) under accounts/* namespace
│   ├── transactions.py    6 tools (5 read, 1 write) under transactions/* namespace
│   └── identity.py        2 tools (1 read, 1 write) under identity/* namespace
├── client.py        AkahuClient: httpx async client + 3-attempt retry/backoff
├── models.py        Pydantic shapes; aliases handle Akahu's _id / _account fields
├── config.py        AkahuConfig (pydantic-settings, env_prefix="AKAHU_")
├── deps.py          Process-wide AkahuClient cache (get_client / aclose_client)
├── safety.py        @require_write_consent decorator + 3-layer safety
└── formatting.py    format_money, mask_account, parse_iso_date
```

### Sub-server mount pattern

Each tool group is its own `FastMCP("name")` instance defined inside `tools/`,
then mounted at the root in `server.py` via `mcp.mount(sub.server, namespace="...")`.
Tools end up exposed as `<namespace>_<tool>` (e.g. `accounts_list_accounts`).
Adding a new tool means adding `@server.tool` inside one of the existing sub-server
modules; adding a new sub-server means a new file under `tools/` and one
`mcp.mount(...)` line in `server.py`.

### Three-layer write safety

Every write tool is decorated with `@require_write_consent("...", automatable=...)`.
The decorator (in `safety.py`) enforces:

1. **Read-only refusal.** `AKAHU_READ_ONLY=true` (default) raises `ReadOnlyError`
   before any HTTP call.
2. **Per-call elicitation.** Calls `ctx.elicit()` for user confirmation. Decline
   or cancel raises `ElicitationDeclinedError`.
3. **Automation bypass.** If the decorator was called with `automatable=True`
   AND `AKAHU_AUTOMATION_BYPASS=true`, layer 2 is skipped (still logs at INFO).

`bypass_eligible_tools()` is the runtime registry consulted by the startup
banner. `AKAHU_READ_ONLY=true` + `AKAHU_AUTOMATION_BYPASS=true` is rejected at
startup by `AkahuConfig._reject_incoherent_bypass`.

When adding a new write tool, prefer `automatable=False` unless the action is
genuinely idempotent, rate-limited, and free of third-party side effects.

## FastMCP docstring parsing (important)

FastMCP parses Google-style docstrings (`Args:` blocks) into the per-parameter
JSON schema for `tools/list`. But the **`Returns:` block is silently dropped**
from the tool description whenever an `Args:` block is also present. So output
shape documentation must live in the *body paragraph* of the docstring (between
the summary line and the `Args:` block), not in a `Returns:` section.

Established pattern across all 14 tools:

```python
"""Summary line.

Returns {"key": ...} prose describing output shape and any usage context.

Args:
    foo: ...
    bar: ...
"""
```

Verify with: `uv run python -c 'import asyncio; from nz_akahu_mcp.server import build_server; m=build_server(); [print(t.name, ":", t.description) for t in asyncio.run(m.list_tools())]'`.

## Akahu API constraints

- **Personal Apps only.** App-scoped endpoints (`/categories`, `/connections`,
  `/parties`, `/identity/{id}/verify-name`) are unreachable and not exposed.
  Don't add tools for them; they will 403.
- **Two-header auth.** Every request needs `Authorization: Bearer <user_token>`
  and `X-Akahu-Id: <app_token>`. Handled centrally by `AkahuClient`.
- **`Transaction` has no per-transaction currency.** Transactions are formatted
  in NZD (`format_money(amount, "NZD")`). For multi-currency accounts (e.g.
  Wise PHP/USD/EUR), callers must pair the result with `accounts/get_account`
  to read the parent account's currency. This is documented in
  `transactions._summarise`.
- **`format_money(amount, currency="NZD")`**: NZD renders with `$` symbol;
  any other ISO code renders as `<CODE> 1,234.56` (e.g. `USD 100.00`); empty
  currency falls back to NZD.
- **Account numbers are masked** via `mask_account` (`01-1234-1234567-00` ->
  `01-****-***4567-00`). All tools surfacing accounts must use it.

## Testing patterns

- `tests/conftest.py` provides three env fixtures: `fake_env` (read-only,
  default), `writable_env` (writes enabled, every write elicits), `bypass_env`
  (writes enabled, automatable writes skip elicit).
- `ctx_factory()` from conftest builds a mock FastMCP `Context` whose `elicit()`
  resolves to `"accept"` | `"decline"` | `"cancel"`. Used to test all three
  outcomes of every write tool.
- HTTP traffic is intercepted with `respx_mock` (base_url scoped to Akahu).
- `load_fixture("name")` reads `tests/fixtures/name.json`.
- Tests for tool modules typically patch `deps.get_client` to inject a
  `MagicMock` with `AsyncMock` methods (see `_fake_client()` in
  `test_accounts.py`).

When adding a new tool, follow the existing pattern: cover the happy path,
empty/None edge cases, and (for writes) all three elicit outcomes plus
read-only refusal.

## Distribution

Single channel: **PyPI** (`uvx nz-akahu-mcp` / `pip install nz-akahu-mcp`).
No Claude Code marketplace plugin, no bundled skill, no project-scope
`.mcp.json` shipped in the repo (gitignored).

Release flow is documented in `PUBLISHING.md`. Summary: bump
`pyproject.toml` `version`, tag `vX.Y.Z`, push, publish GitHub Release.
Trusted Publishing (OIDC) handles PyPI auth; no API tokens in repo secrets.

## Style conventions (from user's global instructions)

- **No emojis** in code, comments, commit messages, or documentation.
- **No em dashes (`—`)** in writing; use hyphens (`-`) or restructure sentences.
- **Humble language**: avoid claiming "success" without verification. Use
  "Implemented X, ready for testing" rather than "Successfully implemented X".
- **Comments explain WHY**, not WHAT. Default to no comments.
- **Review before changing**: when asked to review or analyze, do that first
  and report findings before making changes.

## Sub-agent style note

When working in this repo, the user has expressed preference for tight,
spec-style docstrings/comments and is allergic to decisioning history,
audit-trail prose, and roadmap chatter in permanent docs. Keep docs functional
("what it does, how to use it"), not retrospective ("why we picked this over X").
