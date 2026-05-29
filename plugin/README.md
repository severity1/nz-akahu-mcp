# nz-akahu-mcp (Claude Code plugin)

This plugin packages [`nz-akahu-mcp`](https://github.com/severity1/nz-akahu-mcp) for installation in **Claude Code** via the severity1 marketplace. It exposes 14 MCP tools for the Akahu open-finance API (NZ), with credentials prompted at install and stored in your OS keychain (macOS Keychain on macOS, Windows Credential Manager on Windows). See the [main repo README](https://github.com/severity1/nz-akahu-mcp#readme) for tool reference and architecture details.

> **Claude Desktop users:** use the `.mcpb` Desktop Extension instead - see the [main README](https://github.com/severity1/nz-akahu-mcp#install-in-claude-desktop). Claude Desktop has no UI to configure marketplace-plugin `userConfig` values ([anthropics/claude-code#39455](https://github.com/anthropics/claude-code/issues/39455), [#39827](https://github.com/anthropics/claude-code/issues/39827)).

## Prerequisites

1. **Akahu Personal App + User token** - register at https://my.akahu.nz/developers
2. **[`uv`](https://docs.astral.sh/uv/)** on `PATH` so `uvx` can launch the server
3. **Claude Code** (v2.1.83 or later)

## Install in Claude Code

```text
/plugin marketplace add severity1/severity1-marketplace
/plugin install nz-akahu-mcp@severity1-marketplace
```

You will be prompted for four values:

| Field | What it is | Default |
| --- | --- | --- |
| Akahu User Token | User token from the Akahu developer console | (none) |
| Akahu App Token | App token from the Akahu developer console | (none) |
| Read-only mode | `true` refuses every write tool | `true` |
| Automation bypass | `true` skips consent for safe writes (refresh only) | `false` |

The two tokens are stored in your OS keychain (macOS Keychain / Windows Credential Manager); they never land in plaintext config. The safety defaults give you a read-only server out of the box.

After install: `/mcp` should show `nz-akahu-mcp` connected. Ask Claude *"what accounts do I have?"* to confirm tokens reached the server.

### Reconfigure later

`/plugin` -> Installed -> nz-akahu-mcp -> Configure options. Useful for flipping `read-only` to `false` when you need a refresh, then back to `true`.

## Verifying the install

- `/mcp` lists `nz-akahu-mcp` as connected
- Ask Claude to run a read tool (e.g. `acct_list_accounts`): it returns masked account details
- With defaults (`read-only=true`), any write tool refuses with `ReadOnlyError` before any HTTP call

## Updating

```text
/plugin marketplace update severity1-marketplace
```

The plugin pins `uvx nz-akahu-mcp` (latest published PyPI version), so package updates flow in on next launch without a marketplace update. A marketplace update only ships changes to `plugin.json` / `.mcp.json` / this README.

## Uninstall

```text
/plugin uninstall nz-akahu-mcp@severity1-marketplace
```

Removes the userConfig values from your OS keychain.

## Manual install (non-plugin path)

If you'd rather wire the server yourself with `claude mcp add` or `claude_desktop_config.json`, see the install sections in the [main repo README](https://github.com/severity1/nz-akahu-mcp#readme).
