# Generic deployment examples

These examples show one way to run the authenticated Streamable HTTP transport
behind an HTTPS reverse proxy. They are generalized operator guidance, not a
recommendation to expose banking data publicly without a clear threat model.

Stdio remains the simplest local transport. If you use HTTP, keep the MCP
process bound to loopback, terminate HTTPS at a trusted reverse proxy, and keep
app-level authentication enabled with either a bearer token or an allowlisted
Google OAuth configuration.

## Example files

- `deploy/caddy/nz-akahu-mcp.caddy.example` terminates HTTPS and proxies to
  `127.0.0.1:8091`.
- `deploy/linux-systemd/nz-akahu-http.service` runs the HTTP entrypoint from an
  installed virtual environment under `/opt/nz-akahu-mcp`.
- `deploy/linux-systemd/nz-akahu.env.example` shows placeholder-only runtime
  settings for bearer mode and the OAuth alternative.

## Secret handling

Store real Akahu tokens, bearer tokens, and OAuth client secrets outside the
repository. A typical Linux host would keep `/opt/nz-akahu-mcp/nz-akahu.env`
owned by `root:nz-akahu-mcp` or the service account and readable only by that
owner/group.

Do not commit `.env` files, Google client secret downloads, bearer tokens, or
Akahu token material. The examples use `<TOKEN>`, `<CLIENT_ID>`, and
`<CLIENT_SECRET>` placeholders only.

## Operator checklist

1. Install the package or create a virtual environment under `/opt/nz-akahu-mcp`.
2. Copy `deploy/linux-systemd/nz-akahu.env.example` to
   `/opt/nz-akahu-mcp/nz-akahu.env` and replace placeholders at runtime only.
3. Keep `NZ_AKAHU_MCP_HTTP_HOST=127.0.0.1`.
4. Choose exactly one inbound auth mode:
   - Bearer: set `NZ_AKAHU_MCP_AUTH_MODE=bearer` and
     `NZ_AKAHU_MCP_BEARER_TOKEN=<TOKEN>`.
   - OAuth: set `NZ_AKAHU_MCP_AUTH_MODE=oauth`, configure Google Web
     application credentials, and set either `NZ_AKAHU_MCP_ALLOWED_USERS` or
     `NZ_AKAHU_MCP_ALLOWED_DOMAINS`.
5. Put an HTTPS reverse proxy in front of the loopback listener.
6. Start the service and confirm unauthenticated requests are rejected.

## Validation commands

Run the project checks before deploying a changed checkout:

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest
uv run bandit -r src
uv run pip-audit
```

Check the local service and reverse proxy after installation:

```bash
systemctl status nz-akahu-http
curl -i http://127.0.0.1:8091/mcp
curl -i https://mcp.example.com/mcp
```

In bearer mode, requests without `Authorization: Bearer <TOKEN>` should be
rejected. In OAuth mode, inspect the metadata endpoints through the public HTTPS
hostname:

```bash
curl -fsS https://mcp.example.com/.well-known/oauth-authorization-server | python -m json.tool
curl -fsS https://mcp.example.com/.well-known/oauth-protected-resource/mcp | python -m json.tool
```

Connector clients should use the MCP transport URL, for example
`https://mcp.example.com/mcp`. Do not point connector clients directly at
Google OAuth endpoints.
